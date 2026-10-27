"""M3 reviewed resource candidate; provisioning is exercised only by owned CI."""
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets

from provision_v2 import Admin, desired_topics, provision
from routes import permissions_v2, physical_topic_v2, physical_topic_v3, validate_v2

MANIFEST = 'components/rocketmq/serverd-routes-m3-v2.json'
DIAGNOSTIC_KINDS = {'RuntimeError','ValueError','TimeoutError','AttributeError','TypeError',
    'ForbiddenException','UnauthorizedException','BadRequestException','IllegalStateException','IllegalArgumentException',
    'ClientException','Exception','other'}
DIAGNOSTIC_STATUSES = {40000,40014,40100,40300,40400,40401,50000,50001,50400}


def manifest(repo):
    value = json.loads((repo / MANIFEST).read_text())
    validate_v2(value)
    return value


def bootstrap_manifest(document):
    """Development-only two-owner direct-denial reproduction; never the full gate."""
    value=copy.deepcopy(document)
    roles=('m3-iam','m3-qs-mongo')
    ids={route for role in roles for route in value['accounts'][role]['publish']+value['accounts'][role]['subscriptions']}
    value['routes']=[r for r in value['routes'] if r['id'] in ids]
    value['accounts']={role:value['accounts'][role] for role in roles}
    validate_v2(value)
    return value


def resource_documents(repo, profile, transition):
    original = manifest(repo)
    if transition:
        if profile != 'full':
            raise ValueError('readable transition requires full owned resource profile')
        from readable_transition import validate_transition
        current = json.loads((repo / 'components/rocketmq/serverd-routes-readable-v3.json').read_text())
        validate_transition(original, current)
        return current, original, 'components/rocketmq/serverd-routes-readable-v3.json'
    return (bootstrap_manifest(original) if profile == 'bootstrap' else original), None, MANIFEST


def conflict_route(document, identity, topic, message_type):
    route = dict(id=identity, topic=topic, subscription='', message_type=message_type,
                 owner='iam.mysql', route_revision='m3-1', consumer_group='')
    readable = document['version'] == 3
    route['physical_topic'] = (physical_topic_v3 if readable else physical_topic_v2)(
        topic, message_type, 'iam.mysql', 'm3-1')
    if readable:
        route['naming_scheme'] = 'readable-v1'
    return route


def expected_cases(document):
    """ACLs grant Topic and Group independently; check effective resources honestly."""
    rows = {r['id']:r for r in document['routes']}
    topics = {r['physical_topic']:r for r in rows.values()}
    # Keep pinned wire status values independent from optional client imports.
    result = {'tls/verified_ca_and_san':'allowed','tls/wrong_ca':'rejected',
        'tls/wrong_san':'rejected','tls/plaintext':'rejected',
        'tls/verified_control_after_negatives':'allowed'}
    for role, grants in document['accounts'].items():
        result[role+'/authentication/before'] = 'allowed'
        result[role+'/authentication/after'] = 'allowed'
        allowed = {rows[i]['physical_topic'] for i in grants['publish']}
        permissions = permissions_v2(document,grants)
        for physical, row in sorted(topics.items()):
            result[role+'/publish/'+row['id']] = 'allowed' if physical in allowed else 40100
            if physical in allowed:
                result[role+'/type/'+row['id']] = 40014
        for row in rows.values():
            if row['consumer_group']:
                permitted = ('Sub' in permissions.get('Topic:'+row['physical_topic'],())
                    and 'Sub' in permissions.get('Group:'+row['consumer_group'],()))
                result[role+'/subscribe/'+row['id']] = 'allowed' if permitted else 40100
    return result


def parse_receipt(output, document, *, partial=False):
    marker = 'M3_RESOURCE_RECEIPT '
    receipts = [line.split(marker,1)[1] for line in output.splitlines() if line.startswith(marker)]
    if len(receipts) != 1 or len(receipts[0]) > 32768:
        raise RuntimeError('one bounded resource proof required')
    value = json.loads(receipts[0])
    expected = expected_cases(document)
    diagnostic = value.get('diagnostic')
    phases = {'native_started'} | expected.keys() | {'queue_lookup:'+r['id'] for r in document['routes']} | {
        'producer_bootstrap:'+role+suffix for role in document['accounts']
        for suffix in ('','/route','/startup','/settings')}
    valid_diagnostic = (diagnostic is None if value.get('failed') == 0 else
        isinstance(diagnostic,dict) and set(diagnostic)=={'phase','kind','status'}
        and isinstance(diagnostic['phase'],str) and diagnostic['phase'] in phases
        and isinstance(diagnostic['kind'],str) and diagnostic['kind'] in DIAGNOSTIC_KINDS
        and (diagnostic['status'] is None or type(diagnostic['status']) is int
             and diagnostic['status'] in DIAGNOSTIC_STATUSES))
    if (set(value) != {'client','passed','failed','skipped','cases','scope','diagnostic','denial_path'}
        or value.get('denial_path') != 'direct_signed_send_receive_rpc'
        or value['client'] != '5.1.2' or type(value['passed']) is not int
        or not isinstance(value['cases'],dict) or type(value['failed']) is not int
        or value['failed'] not in (0,1) or type(value['skipped']) is not int or value['skipped'] != 0
        or value['passed'] != len(value['cases'])
        or not valid_diagnostic
        or any(key not in expected or result != expected[key] for key,result in value['cases'].items())
        or (not partial and (value['cases'] != expected or value['failed'] != 0))
        or value['scope'] != 'isolated_transport_acl_and_broker_type_only'):
        raise RuntimeError('resource ACL/type/TLS proof incomplete or substituted')
    return value


def run_resources(repo, directory, broker, project, grpc_port, ca, run, native_run, proof):
    if not project.startswith('rocketmq-m2-') or not broker.startswith(project+'-'):
        raise RuntimeError('owned Compose fixture required')
    profile=os.environ.get('ROCKETMQ_M3_RESOURCE_PROFILE','full')
    if profile not in ('full','bootstrap'):
        raise ValueError('explicit full/bootstrap resource profile required')
    transition_mode = os.environ.get('ROCKETMQ_READABLE_TRANSITION', '0')
    if transition_mode not in ('0', '1'):
        raise ValueError('explicit readable resource transition profile required')
    document, previous_document, source_manifest = resource_documents(repo, profile, transition_mode == '1')
    retirement_mode = os.environ.get('ROCKETMQ_READABLE_RETIREMENT', '0')
    if retirement_mode not in ('0', '1') or (retirement_mode == '1' and previous_document is None):
        raise ValueError('owned retirement requires the full readable resource transition')
    proof['profile']=profile
    proof['full_gate']=False
    proof['readable_transition'] = previous_document is not None
    proof['manifest_version'] = document['version']
    accounts = {role:dict(username='m3-'+secrets.token_hex(8),password=secrets.token_hex(32))
        for role in document['accounts']}
    proof['manifest_sha256'] = hashlib.sha256((repo/source_manifest).read_bytes()).hexdigest()
    proof['active_manifest_sha256']=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    proof['phase'] = 'dependency_warmup'
    # Do not charge uv downloads/builds to the actual TLS process lifetime.
    # Missing dependencies still fail this required profile.
    run(['uv','sync','--locked','--project',str(repo/'scripts/rocketmq/txprobe')],timeout=300)
    proof['dependencies_ready'] = True
    wrong_ca = directory/'m3-wrong-ca.crt'
    run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
        '-subj','/CN=isolated-wrong-root','-keyout',str(directory/'m3-wrong-ca.key'),'-out',str(wrong_ca)])
    config = directory/'m3-resources-private.json'
    config.write_text(json.dumps(dict(endpoint=f'127.0.0.1:{grpc_port}',ca=str(ca),
        wrong_ca=str(wrong_ca),accounts=accounts,manifest=document,
        permissions={role:{resource:sorted(actions) for resource,actions in permissions_v2(document,grants).items()}
                     for role,grants in document['accounts'].items()})))
    config.chmod(0o600)
    env = dict(os.environ, GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=str(ca))
    argv = ['uv','run','--locked','--no-sync','--project',str(repo/'scripts/rocketmq/txprobe'),
        'python',str(repo/'scripts/rocketmq/m3_resource_probe.py'),'--config',str(config)]
    # TLS failure must be visible before the relatively slow MQAdmin provisioning.
    proof['phase'] = 'tls_preflight'
    previous = set(directory.glob('probe-*.log'))
    try:
        tls = native_run(argv+['--tls-only'],cwd=repo,env=env,timeout=60,required=False)
    finally:
        logs = set(directory.glob('probe-*.log'))-previous
        if len(logs) == 1:
            raw = logs.pop().read_bytes()
            proof['tls_private_output_sha256'] = hashlib.sha256(raw).hexdigest()
            allowed = {'native_started'} | {k for k in expected_cases(document) if k.startswith('tls/')}
            proof['tls_progress'] = [line.removeprefix('M3_RESOURCE_STAGE ') for line in raw[-32768:].decode(errors='replace').splitlines()
                if line.startswith('M3_RESOURCE_STAGE ') and line.removeprefix('M3_RESOURCE_STAGE ') in allowed][-8:]
    proof['tls_preflight'] = parse_receipt(tls.stdout,document,partial=True)
    if (tls.returncode or proof['tls_preflight']['failed']
        or set(proof['tls_preflight']['cases']) != {k for k in expected_cases(document) if k.startswith('tls/')}):
        raise RuntimeError('TLS-only preflight failed before resource mutation')
    proof['phase'] = 'provision'
    provision_options = {}
    if previous_document is not None:
        proof['previous_provision'] = provision(broker, previous_document, accounts)
        provision_options['previous'] = previous_document
    proof['provision'] = provision(broker,document,accounts, **provision_options)
    proof['idempotent'] = provision(broker,document,accounts, **provision_options)
    if proof['idempotent']['operations'] != 0:
        raise RuntimeError('production candidate provisioning not idempotent')
    proof['conflicts_refused_without_mutation']=[]
    proof['typed_topics']={k:v['message_type'] for k,v in desired_topics(document).items()}
    if profile=='full':
        # Preserve the five existing subjects and their old/new union. Generic
        # conflict controls use separately owned new-only subjects, so old grants
        # cannot accidentally be the reason an intended negative test fails.
        conflict_accounts = accounts
        if previous_document is not None:
            conflict_accounts = {role: dict(username='control-' + secrets.token_hex(8),
                password=secrets.token_hex(32)) for role in accounts}
            proof['new_only_control_provision'] = provision(broker, document, conflict_accounts)
            proof['conflict_controls_use_separate_principals'] = True
        reader = Admin(broker)
        snapshot = '/tmp/m3-resource-snapshot-'+secrets.token_hex(6)
        reader.docker('mkdir','-m','700',snapshot)
        try:
            before, users = reader.metadata(snapshot), reader.users()
            acls = {role:reader.acl(account['username']) for role,account in conflict_accounts.items()}
            def unchanged(metadata):
                return (reader.metadata(snapshot) == metadata and reader.users() == users
                    and all(reader.acl(conflict_accounts[role]['username']) == grants for role,grants in acls.items()))
            # Submit a missing candidate together with a conflicting existing queue
            # or credential; the entire preflight must reject before any mutation.
            for kind in ('queues','credentials','acl'):
                candidate = copy.deepcopy(document)
                role = next(iter(conflict_accounts))
                missing = conflict_route(document, 'never-create', 'infra.m3.never-created', 'NORMAL')
                candidate['routes'].append(missing)
                candidate['accounts'][role]['publish'].append(missing['id'])
                credentials = copy.deepcopy(conflict_accounts)
                if kind == 'queues':
                    candidate['topic_options']['read_queue_nums'] = 2
                elif kind == 'credentials':
                    credentials[role]['password'] = secrets.token_hex(32)
                else:
                    candidate['accounts'][role]['subscriptions'] = []
                try:
                    provision(broker,candidate,credentials)
                except RuntimeError as error:
                    reason = {'queues':'existing topic type or configuration conflicts',
                        'credentials':'existing principal differs; credential rotation refused',
                        'acl':'existing principal ACL exceeds or conflicts with reviewed grants'}[kind]
                    if str(error) != 'v2 provision: '+reason:
                        raise RuntimeError('conflict proof failed for an unexpected preflight reason') from None
                else:
                    raise RuntimeError('conflicting candidate unexpectedly provisioned')
                if not unchanged(before):
                    raise RuntimeError('conflicting preflight mutated Broker resources')
            proof['conflicts_refused_without_mutation'] = ['queues','credentials','acl']
            # A separate sentinel has deliberately conflicting type metadata. Never
            # alter a candidate business Topic, even inside this isolated fixture.
            sentinel = conflict_route(document, 'type-conflict', 'infra.m3.type-conflict', 'TRANSACTION')
            reader('updateTopic','-t',sentinel['physical_topic'],'-r','1','-w','1',
                '-p','6','-a','+message.type=NORMAL',mutation=True)
            before = reader.metadata(snapshot)
            candidate = copy.deepcopy(document)
            candidate['routes'].extend([sentinel,missing])
            candidate['accounts'][role]['publish'].extend([sentinel['id'],missing['id']])
            try:
                provision(broker,candidate,conflict_accounts)
            except RuntimeError as error:
                if str(error) != 'v2 provision: existing topic type or configuration conflicts':
                    raise RuntimeError('type proof failed for an unexpected preflight reason') from None
            else:
                raise RuntimeError('conflicting type unexpectedly provisioned')
            if not unchanged(before):
                raise RuntimeError('type preflight mutated Broker resources')
            proof['conflicts_refused_without_mutation'].append('type')
            proof['typed_topics'] = {k:v['message_type'] for k,v in desired_topics(document).items()}
        finally:
            for name in ('topic.json','subscriptionGroup.json'):
                reader.docker('rm','-f','--',snapshot+'/'+name,required=False)
            reader.docker('rmdir',snapshot)
    proof['phase'] = 'native_acl_and_type'
    result = native_run(argv,
        cwd=repo,env=env,timeout=900,required=False)
    raw = result.stdout+result.stderr
    private = directory/'m3-resource-probe.log'
    private.write_text(raw);private.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['native_partial'] = parse_receipt(result.stdout,document,partial=True)
    proof['native_receipt'] = parse_receipt(result.stdout,document)
    if result.returncode:
        raise RuntimeError('isolated resource probe failed')
    proof['phase'] = 'complete'
    proof['full_gate'] = profile=='full'
    proof['scope'] = 'reviewed production names in an isolated Broker; production resources and runtime unchanged'
    if previous_document is not None:
        proof['scope'] += '; original five subjects retain exact old/new union, conflict controls use distinct new-only subjects'
        proof['credential_rotation'] = False
    if retirement_mode == '1':
        from readable_retirement_native import run_owned_retirement
        proof['phase'] = 'owned_empty_retirement'
        from pop_retry_sentinel import route_and_roles, receipt as sentinel_receipt
        sentinel_route, _, _ = route_and_roles(json.loads(config.read_bytes()))
        native = run([*argv[:argv.index('python') + 1],
            str(repo / 'scripts/rocketmq/pop_retry_sentinel.py'), '--config', str(config),
            '--project', project], cwd=repo, env=env, timeout=90, required=False)
        if native.returncode:
            proof['pop_sentinel_exit_code'] = native.returncode
            proof['pop_sentinel_output_sha256'] = hashlib.sha256((native.stdout + native.stderr).encode()).hexdigest()
            raise RuntimeError('owned actual POP sentinel failed; private output withheld')
        sentinel = sentinel_receipt(native.stdout, sentinel_route)
        proof['retirement_fixture'] = run_owned_retirement(
            broker, project, previous_document, document, accounts, proof['native_receipt'],
            pop_v2_sentinel=sentinel)
        proof['phase'] = 'complete'
