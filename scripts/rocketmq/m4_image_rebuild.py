"""Reviewed M4-only source, production messaging packagers and owned materials."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

from audit_transaction_limit import write_private
from image_start_fixture import require
from m4_owned_materials import BASE, ROLES

SOURCES = dict(iam='48182c39424573060fda0e27ed6670d2b326f42d',
               qs='d20436edb363c17f0b177126aebe43a44bc5e082',
               ai='61ef88ac95800dfd3c0c90fd56c102f7c0e77e8f')
BUILDER_SHA = 'edb6087ecf260bc7706ffc9fa823b802d94facbd'
BUILD_RUN = '40282528557'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def root_action(f, action, *extra):
    allowed = ('GITHUB_ACTIONS', 'RUNNER_OS', 'RUNNER_ENVIRONMENT', 'GITHUB_RUN_ID',
               'GITHUB_RUN_ATTEMPT', 'GITHUB_WORKSPACE')
    command = ['sudo', '-n', '--preserve-env=' + ','.join(allowed), 'python3',
               str(f.repo / 'scripts/rocketmq/m4_owned_materials.py'), action,
               '--fixture', str(f.directory), *extra]
    result = f.run(command, timeout=180, required=False)
    if result.returncode:
        reasons = re.findall(r'RuntimeError: ([a-z_]{1,100})\s*$', result.stderr, re.MULTILINE)
        f.report['m4_root_failure'] = dict(action=action, exit_code=result.returncode,
            private_output_sha256=hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest(),
            fixed_reasons=reasons[-2:])
        try:
            diagnostic = json.loads(result.stdout)
            if set(diagnostic) == {'schema','failure_kind','source_frames'} and diagnostic['schema'] == 'm4-owned-helper-failure/v1':
                f.report['m4_root_failure']['diagnostic'] = diagnostic
        except (ValueError,TypeError):
            pass
        raise RuntimeError('owned_m4_root_action_failed')
    return json.loads(result.stdout)


def compose_material_mounts(source, service, variable, revision, role):
    import yaml
    document = yaml.safe_load(source.read_text())
    result = []
    prefix = str(BASE / ROLES[role][0] / 'versions') + '/'
    for row in document['services'][service]['volumes']:
        if not isinstance(row, dict) or not row.get('source', '').startswith(str(BASE) + '/'):
            continue
        row = copy.deepcopy(row)
        expression = r'\$\{' + re.escape(variable) + r':(?:\?|-)[^}]+\}'
        row['source'], count = re.subn(expression, revision, row['source'])
        require(count == 1 and '$' not in row['source'] and row['source'].startswith(prefix + revision + '/'),
                'actual_compose_material_revision_differs')
        require(row['read_only'] is True and row['bind']['create_host_path'] is False,
                'actual_compose_material_write_refused')
        result.append(row)
    require(len(result) == 3, 'actual_compose_three_material_files_required')
    return result


def projected_mounts(iam_source, qs_source, revision):
    return {
        'iam': compose_material_mounts(iam_source / 'build/docker/docker-compose.prod.yml',
            'iam-apiserver', 'ROCKETMQ_BINDING_REVISION', revision, 'iam'),
        'worker': compose_material_mounts(qs_source / 'build/docker/docker-compose.prod.yml',
            'runtime', 'ROCKETMQ_WORKER_BINDING_REVISION', revision, 'worker'),
        'collection': [],
    }


def owner_limits(workers, queue, batch, *, sends=4, python=False):
    return dict(sends=sends, branches=16, check_workers=workers, check_queue=queue,
                reconcile_batch=batch, check_timeout=2 if python else '2s',
                rpc_timeout=5 if python else '5s', lease=60 if python else '60s',
                reconcile_interval=5 if python else '5s')


def replace_fixture_config(path, value):
    # These are not audit receipts or production files: the earlier owned
    # preparation created them and no application has started yet.
    require(path.is_file() and not path.is_symlink(), 'existing_owned_config_required')
    path.write_text(json.dumps(value, indent=2) + '\n')


def bridge_binding(domain, revision):
    transport = copy.deepcopy(domain)
    transport['transactions'] = {'qs.mysql': transport['transactions']['qs.mysql']}
    # Binding JSON is decoded by encoding/json: Go durations are nanoseconds.
    # YAML/viper duration strings remain in the domain configuration. Convert
    # only the fixed budget; do not normalize StoreID, epoch or message bytes.
    limits = transport['transactions']['qs.mysql']['limits']
    for field, text, nanos in [('check_timeout','2s',2_000_000_000),
                              ('rpc_timeout','5s',5_000_000_000),
                              ('lease','60s',60_000_000_000),
                              ('reconcile_interval','5s',5_000_000_000)]:
        require(limits[field] == text or (type(limits[field]) is int and limits[field] == nanos),
                'actual_bridge_fixed_duration_required')
        limits[field] = nanos
    return dict(binding_revision=revision, enabled=True, provider='rocketmq', publish_enabled=False,
                rocketmq=transport, max_in_flight=1,
                signing_key_file='/run/qs-server-jose/qs.sign.fixture.json',
                decrypt_key_files={'qs.encrypt.fixture': '/run/qs-server-jose/qs.encrypt.fixture.json'},
                ai_signer_files={'ai.sign.fixture': '/run/qs-server-jose/ai.sign.fixture.json'},
                ai_recipient_key_file='/run/qs-server-jose/ai.encrypt.fixture.json')


def api_configuration(source, config, revision):
    renderer = load(source / 'scripts/cd/render-api-messaging.py', 'actual_qs_messaging_renderer')
    env = dict(MESSAGING_PROVIDER='rocketmq', ROCKETMQ_ENDPOINT='broker:8081', ROCKETMQ_INSTANCE_ID='qs-apiserver-1',
               ROCKETMQ_PUBLISH_ENABLED='false', ROCKETMQ_MYSQL_STORE_ID='isolated-qs-mysql-primary',
               ROCKETMQ_MYSQL_WRITER_EPOCH='m3-1', ROCKETMQ_MONGO_STORE_ID='isolated-qs-mongo-primary', ROCKETMQ_MONGO_WRITER_EPOCH='m3-1')
    config['messaging'] = renderer.production_binding(env)
    subscription = copy.deepcopy(config['messaging']['rocketmq']); subscription.update(transactions={}, publish_enabled=False)
    config['iam']['authz-sync'].update(provider='rocketmq', rocketmq=subscription)
    return bridge_binding(config['messaging']['rocketmq'], revision)


def configure(f, args, ai_env, case, *, expected_qs_sha=None):
    f.stage = 'actual_m4_packagers_and_synthetic_materials'
    revision = 'm4-owned-' + f.project.rsplit('-', 1)[1]
    sources = f.directory / 'm4-material-source'; sources.mkdir(mode=0o700)
    plan = dict(schema='m4-synthetic-image-materials/v1', project=f.project, revision=revision, files=[], api_binding=None)
    def material(role, relative, raw):
        path = sources / role / relative; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(raw); path.chmod(0o600)
        plan['files'].append(dict(role=role, relative=relative, source=str(path), sha256=hashlib.sha256(raw).hexdigest()))
    for role in ROLES:
        private = f.private_dirs[role]
        credentials = {'iam': 'iam-credentials.json', 'api': 'qs-credentials.json',
                       'ai': 'credentials.json', 'worker': 'worker-credentials.json'}[role]
        for source, target in [(credentials, 'credentials.json'), ('mq-ca.crt', 'ca.crt'), ('routes.json', 'routes.json')]:
            material(role, 'rocketmq/' + target, (private / source).read_bytes())
        if role == 'api': material(role, 'rocketmq/mongo-credentials.json', (private / 'mongo-credentials.json').read_bytes())
        if role not in ('api', 'ai'): continue
        for kid, old in [('qs.sign', 'qs-sign'), ('qs.encrypt', 'qs-recipient'), ('ai.sign', 'ai-sign'), ('ai.encrypt', 'ai-decrypt')]:
            private_key = kid.startswith('qs.') if role == 'api' else kid.startswith('ai.')
            key = json.loads((private / (old + ('-private.json' if private_key else '-public.json'))).read_bytes())
            key['kid'] = kid + '.fixture'
            material(role, kid + '.fixture.json', json.dumps(key, sort_keys=True).encode())
    iam_path = f.private_dirs['iam'] / 'runtime.json'; iam = json.loads(iam_path.read_bytes())
    iam_renderer = load(args.sources / 'iam/scripts/cd/render-messaging.py', 'actual_iam_messaging_renderer')
    iam['messaging'] = iam_renderer.production_binding(dict(IAM_MESSAGING_PROVIDER='rocketmq', ROCKETMQ_ENDPOINT='broker:8081',
        ROCKETMQ_INSTANCE_ID='iam-primary-1', ROCKETMQ_BINDING_REVISION=revision,
        ROCKETMQ_STORE_ID='isolated-iam-primary', ROCKETMQ_WRITER_EPOCH='m3-1', ROCKETMQ_PUBLISH_ENABLED='false'))
    replace_fixture_config(iam_path, iam)
    api_path = f.private_dirs['api'] / 'runtime.json'; api = json.loads(api_path.read_bytes())
    plan['api_binding'] = api_configuration(args.sources / 'qs', api, revision)
    replace_fixture_config(api_path, api)
    worker_path = f.private_dirs['worker'] / 'runtime.json'; worker = json.loads(worker_path.read_bytes())
    import yaml
    # This consumer has no renderer: use the actual source profile, changing only
    # the owned endpoint and stable fixture instance before its real decoder.
    worker['messaging'] = yaml.safe_load((args.sources / 'qs/configs/worker.prod.yaml').read_text())['messaging']
    worker['messaging']['rocketmq'].update(endpoint='broker:8081', instance_id='qs-worker-owned')
    require(worker['messaging']['rocketmq']['transactions'] == {} and worker['messaging']['rocketmq']['publish_enabled'] is False,
            'actual_worker_must_remain_consumer_only')
    require(worker['worker']['concurrency'] == 48, 'actual_worker_original_concurrency_required')
    f.report['actual_source_worker_concurrency'] = 48
    replace_fixture_config(worker_path, worker)
    ai_binding = dict(enabled=True, provider='rocketmq', publish_enabled=False, max_in_flight=1, binding_revision=revision,
        rocketmq=dict(endpoint='broker:8081', credentials_file='/run/qs-ai-rocketmq/credentials.json',
                      ca_file='/run/qs-ai-rocketmq/ca.crt', routes_file='/run/qs-ai-rocketmq/routes.json'),
        signing_key_file='/run/qs-ai-jose/ai.sign.fixture.json', decrypt_key_files={'ai.encrypt.fixture': '/run/qs-ai-jose/ai.encrypt.fixture.json'},
        qs_signer_files={'qs.sign.fixture': '/run/qs-ai-jose/qs.sign.fixture.json'}, qs_recipient_key_file='/run/qs-ai-jose/qs.encrypt.fixture.json',
        transactions={'ai.mysql': dict(store_id='isolated-ai-primary', writer_epoch='m3-1', route_revision='m3-1', limits=owner_limits(1,16,100,python=True))})
    ai_export = load(args.sources / 'ai/scripts/cd/deploy.py', 'actual_ai_deployment_packager')
    runtime = dict(services={'qs-ai': {'environment': {}}})
    ai_export.bind_messaging(runtime, json.dumps(ai_binding))
    # Exercise Compose's actual $$ processing, not a hand-written unescape.
    runtime['services']['qs-ai']['image'] = f.images['ai']
    runtime_file = f.directory / 'ai-actual-messaging-compose.json'; write_private(runtime_file, runtime)
    effective = json.loads(f.run(['docker','compose','-f',str(runtime_file),'config','--format','json']).stdout)
    ai_service = effective['services']['qs-ai']; ai_env.update(ai_service['environment'])
    require(json.loads(ai_env['QS_AI_MESSAGING']) == {k:v for k,v in ai_binding.items() if k!='binding_revision'},
            'actual_compose_ai_binding_bytes_differ')
    write_private(f.directory / 'm4-plan.json', plan)
    f.runtime_mounts = projected_mounts(args.sources / 'iam', args.sources / 'qs', revision)
    f.runtime_mounts['ai'] = ai_service['volumes']
    f.report['m4_material_stage'] = root_action(f, 'stage'); f.m4_materials = True
    case('actual_three_source_packagers_and_root_owned_twenty_one_material_files')
    # Actual host freeze tool -> ordinary native preflight image -> output config.
    # Repeat freezes the exact same image/config again, without syncing/stopping.
    native = root_action(f, 'api', '--source', str(args.sources / 'qs'), '--image', f.images['api'])
    require(native['result']['source_sha'] == (expected_qs_sha or SOURCES['qs']) and native['native_metadata']['final_transaction_binding'] is True,
            'actual_current_api_final_preflight_required')
    f.runtime_mounts['api'] = native['volumes']
    f.report['m4_api_native_preflight'] = native
    case('actual_current_api_host_freeze_and_native_preflight_repeated')
