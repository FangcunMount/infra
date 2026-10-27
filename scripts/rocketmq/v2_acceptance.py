"""Required typed provisioning and shared PUBLIC subscriber acceptance."""
import copy
import hashlib
import json
import secrets
import time

from provision_v2 import Admin
from routes import consumer_group_v2, physical_topic_v2, consumer_group_v3, physical_topic_v3, validate


def setup(repo, sdk, broker, project, accounts, directory, admin, run, passed, *, fixture_manifest=None, readable=False):
    version = 3 if readable else 2
    vectors = repo / f'components/rocketmq/routing-v{version}-vectors.json'
    if vectors.read_bytes() != (sdk / f'contracts/rocketmq-routing-v{version}.json').read_bytes():
        raise RuntimeError('SDK/infra canonical route vectors differ')
    passed(f'v{version}_go_python_infra_exact_route_vectors')
    manifest = (json.loads((repo / 'components/rocketmq/test-routes-v2.json').read_text())
                if fixture_manifest is None else copy.deepcopy(fixture_manifest))
    topic_name = physical_topic_v3 if readable else physical_topic_v2
    group_name = consumer_group_v3 if readable else consumer_group_v2
    if readable:
        manifest['version'] = 3
        for route in manifest['routes']:
            route['naming_scheme'] = 'readable-v1'
            route['physical_topic'] = topic_name(route['topic'],route['message_type'],route['owner'],route['route_revision'])
            route['consumer_group'] = group_name(route['topic'],route['subscription']) if route.get('subscription') else ''
    validate(manifest)
    secret = directory / 'sdk-v2-credentials.json'
    secret.write_text(json.dumps(accounts)); secret.chmod(0o600)
    def provision(document):
        path = directory / ('manifest-' + secrets.token_hex(5) + '.json')
        path.write_text(json.dumps(document)); path.chmod(0o600)
        return run(['python3', str(repo / 'scripts/rocketmq/provision.py'), '--container', broker,
                    '--project', project, '--manifest', str(path), '--credentials', str(secret)],
                   timeout=900, required=False)
    reader = Admin(broker)
    snapshot_dir = '/tmp/m2-v2-proof-' + secrets.token_hex(8)
    reader.docker('mkdir','-m','700',snapshot_dir)
    try:
        # A type conflict and a missing candidate are submitted together. The
        # existing fixture topic must remain NORMAL; the candidate must NOT appear.
        conflict = copy.deepcopy(manifest)
        conflict['routes'] = []
        for name, revision in (('conflict','negative-existing-type'),('candidate','negative-never-create')):
            route = {'id':name,'topic':'sdk.logical','subscription':'sdk-type-conflict',
                     'message_type':'TRANSACTION','owner':'iam.mysql','route_revision':revision,
                     'physical_topic':topic_name('sdk.logical','TRANSACTION','iam.mysql',revision),
                     'consumer_group':group_name('sdk.logical','sdk-type-conflict')}
            if readable:route['naming_scheme']='readable-v1'
            conflict['routes'].append(route)
        conflict['accounts']={'owner-a':{'owner':'iam.mysql','publish':['conflict','candidate'],'subscriptions':[]}}
        admin('updateTopic','-t',conflict['routes'][0]['physical_topic'],'-r','1','-w','1',
              '-a','+message.type=NORMAL',success=True)
        before, users = reader.metadata(snapshot_dir), reader.users()
        result = provision(conflict)
        if (result.returncode == 0 or "existing topic type or configuration conflicts" not in result.stderr
                or reader.metadata(snapshot_dir) != before or reader.users() != users):
            raise RuntimeError('conflicting type did not refuse every Broker resource mutation')
        passed('v2_existing_type_conflict_refuses_all_resource_mutations')
        initial = provision(manifest)
        if initial.returncode:
            diagnostic = next((line for line in initial.stderr.splitlines() if line.startswith('RuntimeError: ')), '')
            # Only our fixed diagnostic phrases may leave the private capture.
            safe = ('private Broker operation', 'Broker administrative operation',
                    'Broker mutation missing', 'metadata snapshot missing',
                    'unrecognized pinned Broker', 'unrecognized private',
                    'authoritative principal', 'existing principal',
                    'post-provision readback', 'duplicate principal',
                    'Broker v2 provision lock', 'existing topic', 'existing subscription', 'v2 provision')
            if diagnostic.removeprefix('RuntimeError: ').startswith(safe):
                raise RuntimeError(diagnostic)
            raise RuntimeError('v2 fixture provisioning failed (private diagnostics withheld)')
        receipt = json.loads(initial.stdout)
        if not receipt.get('verified') or receipt['operations'] <= 0:
            raise RuntimeError('typed provision readback absent')
        repeated = provision(manifest)
        if repeated.returncode or json.loads(repeated.stdout).get('operations') != 0:
            raise RuntimeError('typed provision is not idempotent')
        passed('v2_idempotent_typed_resources_and_minimum_owner_acls')
        before = reader.metadata(snapshot_dir)
        bad_queues = copy.deepcopy(manifest)
        bad_queues['topic_options']['read_queue_nums'] = 2
        if provision(bad_queues).returncode == 0 or reader.metadata(snapshot_dir) != before:
            raise RuntimeError('existing queue configuration overwritten')
        passed('v2_existing_configuration_conflict_refused')
        proof={'manifest_version':version,'naming_scheme':'readable-v1' if readable else 'hash-v2',
               'route_vectors_sha256':hashlib.sha256(vectors.read_bytes()).hexdigest(),
               'manifest_sha256':hashlib.sha256((repo/'components/rocketmq/test-routes-v2.json').read_bytes()).hexdigest(),
               'effective_manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
               'provision_receipt':receipt,'idempotent_operations':0,
               'typed_topics':{r['physical_topic']:r['message_type'] for r in manifest['routes']},
               'owner_actions':'publishers Pub/Get on their exact owner routes; observer Sub/Get only'}
        return manifest,proof
    finally:
        for name in ('topic.json','subscriptionGroup.json'):
            reader.docker('rm','-f','--',snapshot_dir+'/'+name,required=False)
        reader.docker('rmdir',snapshot_dir)


def denied_owners(start, sql, mongo_command, passed, *, python):
    for language in (('sdk-go','sdk-python') if python else ('sdk-go',)):
        targets = [('mysql','owner-b')]
        if language=='sdk-go':
            targets.append(('mongo','owner-a'))
        for storage, principal in targets:
            identity = 'denied-' + language + '-' + storage
            probe = start(language,'send',identity,storage=storage,principal=principal)
            probe.finish(expected=1)
            if not any(e.get('event')=='broker_denied' for e in probe.events):
                raise RuntimeError('wrong owner failed for a cause other than Broker authorization')
            if any(e.get('event')=='half' for e in probe.events):
                raise RuntimeError('wrong owner reached local executor')
            if storage=='mysql':
                count=sql(f"SELECT COUNT(*) FROM sdk_business WHERE id='{identity}';")
            else:
                count=mongo_command('db.getSiblingDB("sdkprobe").sdk_business.countDocuments({_id:"'+identity+'"})')
            if count!='0':
                raise RuntimeError('wrong owner created a business effect')
        passed('v2_'+language+'_wrong_owner_broker_denied_without_business')


def shared_budget(start, passed, *, language, observe=None):
    suffix='go' if language=='sdk-go' else 'python'
    if observe is not None: observe('baseline', language)
    revision='sdk-v2-shared-'+suffix
    subscription='sdk-shared-'+suffix
    observer=start(language,'shared-consume',revision=revision,subscription=subscription)
    observer.wait('ready')
    if observe is not None: observe('subscribed', language)
    expected=set()
    for storage,mode in (('mysql','send'),('mongo','send'),('mysql','normal')):
        identity='shared-'+suffix+'-'+('normal' if mode=='normal' else storage)
        sender=start('sdk-go',mode,identity,storage=storage,revision=revision,branches=3)
        if mode=='send':
            sender.wait('half');sender.send('commit')
        sender.wait('closed');sender.finish()
        expected.update(identity+'-b'+str(i) for i in range(3))
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        observer.drain()
        entered=[e for e in observer.events if e.get('event')=='handler_enter']
        if len(entered)>=2:
            break
        time.sleep(.05)
    else:
        raise RuntimeError('two real subscriber handlers never entered')
    time.sleep(.25)
    observer.drain()
    entered=[e for e in observer.events if e.get('event')=='handler_enter']
    if len(entered)!=2 or any(e.get('event')=='received' for e in observer.events):
        raise RuntimeError('physical input split amplified the shared in-flight budget')
    if observe is not None: observe('held', language)
    observer.send('release')
    for identity in sorted(expected):
        observer.wait('received',identity,timeout=90)
    observer.send('stop');observer.wait('closed');observer.finish()
    maxima=[int(e['decision']) for e in observer.events if e.get('event')=='max_inflight']
    if maxima!=[2]:
        raise RuntimeError('shared public SDK subscriber maximum was not exactly two')
    observed={e['id'] for e in observer.events if e.get('event')=='received'}
    if observed!=expected:
        raise RuntimeError('unexpected original ID/wire across typed physical inputs')
    if observe is not None: observe('closed', language)
    passed('v2_'+language+'_three_physical_inputs_share_two_handler_budget')
