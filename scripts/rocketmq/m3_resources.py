"""M3 reviewed resource candidate; provisioning is exercised only by owned CI."""
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets

from provision_v2 import Admin, desired_topics, provision
from routes import permissions_v2, physical_topic_v2, validate_v2

MANIFEST = 'components/rocketmq/serverd-routes-m3-v2.json'


def manifest(repo):
    value = json.loads((repo / MANIFEST).read_text())
    validate_v2(value)
    return value


def expected_cases(document):
    """ACLs grant Topic and Group independently; check effective resources honestly."""
    rows = {r['id']:r for r in document['routes']}
    topics = {r['physical_topic']:r for r in rows.values()}
    # Keep pinned wire status values independent from optional client imports.
    result = {'tls/verified_ca_and_san':'allowed','tls/wrong_ca':'rejected',
        'tls/wrong_san':'rejected','tls/plaintext':'rejected',
        'tls/verified_control_after_negatives':'allowed'}
    for role, grants in document['accounts'].items():
        allowed = {rows[i]['physical_topic'] for i in grants['publish']}
        permissions = permissions_v2(document,grants)
        for physical, row in sorted(topics.items()):
            result[role+'/publish/'+row['id']] = 'allowed' if physical in allowed else 40300
            if physical in allowed:
                result[role+'/type/'+row['id']] = 40014
        for row in rows.values():
            if row['consumer_group']:
                permitted = ('Sub' in permissions.get('Topic:'+row['physical_topic'],())
                    and 'Sub' in permissions.get('Group:'+row['consumer_group'],()))
                result[role+'/subscribe/'+row['id']] = 'allowed' if permitted else 40300
    return result


def parse_receipt(output, document, *, partial=False):
    marker = 'M3_RESOURCE_RECEIPT '
    receipts = [line.split(marker,1)[1] for line in output.splitlines() if line.startswith(marker)]
    if len(receipts) != 1 or len(receipts[0]) > 32768:
        raise RuntimeError('one bounded resource proof required')
    value = json.loads(receipts[0])
    expected = expected_cases(document)
    if (set(value) != {'client','passed','failed','skipped','cases','scope'}
        or value['client'] != '5.1.2' or type(value['passed']) is not int
        or not isinstance(value['cases'],dict) or type(value['failed']) is not int
        or value['failed'] not in (0,1) or type(value['skipped']) is not int or value['skipped'] != 0
        or value['passed'] != len(value['cases'])
        or any(key not in expected or result != expected[key] for key,result in value['cases'].items())
        or (not partial and (value['cases'] != expected or value['failed'] != 0))
        or value['scope'] != 'isolated_transport_acl_and_broker_type_only'):
        raise RuntimeError('resource ACL/type/TLS proof incomplete or substituted')
    return value


def run_resources(repo, directory, broker, project, grpc_port, ca, run, native_run, proof):
    if not project.startswith('rocketmq-m2-') or not broker.startswith(project+'-'):
        raise RuntimeError('owned Compose fixture required')
    document = manifest(repo)
    accounts = {role:dict(username='m3-'+secrets.token_hex(8),password=secrets.token_hex(32))
        for role in document['accounts']}
    proof['manifest_sha256'] = hashlib.sha256((repo/MANIFEST).read_bytes()).hexdigest()
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
    argv = ['uv','run','--locked','--project',str(repo/'scripts/rocketmq/txprobe'),
        'python',str(repo/'scripts/rocketmq/m3_resource_probe.py'),'--config',str(config)]
    # TLS failure must be visible before the relatively slow MQAdmin provisioning.
    tls = native_run(argv+['--tls-only'],cwd=repo,env=env,timeout=60,required=False)
    proof['tls_preflight'] = parse_receipt(tls.stdout,document,partial=True)
    if (tls.returncode or proof['tls_preflight']['failed']
        or set(proof['tls_preflight']['cases']) != {k for k in expected_cases(document) if k.startswith('tls/')}):
        raise RuntimeError('TLS-only preflight failed before resource mutation')
    proof['provision'] = provision(broker,document,accounts)
    proof['idempotent'] = provision(broker,document,accounts)
    if proof['idempotent']['operations'] != 0:
        raise RuntimeError('production candidate provisioning not idempotent')
    reader = Admin(broker)
    snapshot = '/tmp/m3-resource-snapshot-'+secrets.token_hex(6)
    reader.docker('mkdir','-m','700',snapshot)
    try:
        before, users = reader.metadata(snapshot), reader.users()
        acls = {role:reader.acl(account['username']) for role,account in accounts.items()}
        def unchanged(metadata):
            return (reader.metadata(snapshot) == metadata and reader.users() == users
                and all(reader.acl(accounts[role]['username']) == grants for role,grants in acls.items()))
        # Submit a missing candidate together with a conflicting existing queue
        # or credential; the entire preflight must reject before any mutation.
        for kind in ('queues','credentials','acl'):
            candidate = copy.deepcopy(document)
            role = next(iter(accounts))
            missing = dict(id='never-create',topic='infra.m3.never-created',subscription='',
                message_type='NORMAL',owner='iam.mysql',route_revision='m3-1',consumer_group='',
                physical_topic=physical_topic_v2('infra.m3.never-created','NORMAL','iam.mysql','m3-1'))
            candidate['routes'].append(missing)
            candidate['accounts'][role]['publish'].append(missing['id'])
            credentials = copy.deepcopy(accounts)
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
        sentinel = dict(id='type-conflict',topic='infra.m3.type-conflict',subscription='',
            message_type='TRANSACTION',owner='iam.mysql',route_revision='m3-1',consumer_group='',
            physical_topic=physical_topic_v2('infra.m3.type-conflict','TRANSACTION','iam.mysql','m3-1'))
        reader('updateTopic','-t',sentinel['physical_topic'],'-r','1','-w','1',
            '-p','6','-a','+message.type=NORMAL',mutation=True)
        before = reader.metadata(snapshot)
        candidate = copy.deepcopy(document)
        candidate['routes'].extend([sentinel,missing])
        candidate['accounts'][role]['publish'].extend([sentinel['id'],missing['id']])
        try:
            provision(broker,candidate,accounts)
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
    proof['scope'] = 'reviewed production names in an isolated Broker; production resources and runtime unchanged'
