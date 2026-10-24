"""Actual five-image startup on owned current schemas and real mTLS peers.

Startup trial only, on independent controlled facts. No C1/cutover/system claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time

from ai_image_start import AI_SHA, KEY_PROGRAM, PYTHON, messaging as ai_messaging, metrics as ai_metrics
from audit_transaction_limit import write_private
from iam_image_start import configuration as iam_configuration, protocol_metrics, seed_receipt, source_failure_markers
from image_start_fixture import require
from m3_resources import manifest
from provision_v2 import provision
from qs_image_pair import QSPairFixture, QS_SHA
from qs_runtime_configuration import configuration as qs_configuration

IAM_SHA = '954ad9dee2f71a51151b696ec05d5cb90cc65b50'
SOURCES = dict(iam=IAM_SHA, qs=QS_SHA, ai=AI_SHA)


def qs_metrics(raw):
    expected = dict(sdk_ready=1, sampler_running=1, observation_available=1,
                    admission_open=0, check_workers_limit=2, check_queue_limit=16)
    for owner in ('qs.mysql', 'qs.mongo'):
        for key, value in expected.items():
            require(f'reliable_messaging_transaction_{key}{{owner="{owner}"}} {value}' in raw.splitlines(), 'actual_qs_owner_metric_required_' + key)
    return {owner: expected.copy() for owner in ('qs.mysql', 'qs.mongo')}


class FiveImageFixture(QSPairFixture):
    def select(self, component):
        self.private = self.private_dirs[component]
        self.image = self.images[component]

    def certificate(self, name, cn, aliases):
        root = self.directory / 'service-tls'
        ext = root / (name + '.ext')
        ext.write_text('subjectAltName=' + ','.join('DNS:' + a for a in aliases) + '\nextendedKeyUsage=serverAuth,clientAuth\n'); ext.chmod(0o600)
        self.run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=' + cn + '/OU=QS',
                  '-keyout', str(root / (name + '.key')), '-out', str(root / (name + '.csr'))])
        self.run(['openssl', 'x509', '-req', '-days', '1', '-in', str(root / (name + '.csr')),
                  '-CA', str(root / 'service-ca.crt'), '-CAkey', str(root / 'service-ca.key'), '-CAcreateserial',
                  '-extfile', str(ext), '-out', str(root / (name + '.crt'))])

    def start(self, component, *, alias, memory, cpus, environment=None, extra=None):
        self.select(component)
        env = self.directory / (component + '-runtime.env')
        fields = environment or {}
        require(all('\n' not in k + str(v) and '=' not in k for k, v in fields.items()), 'single_line_runtime_environment_required')
        env.write_text(''.join(k + '=' + str(v) + '\n' for k, v in fields.items())); env.chmod(0o600)
        self.report.setdefault('runtime_environment_sha256', {})[component] = hashlib.sha256(env.read_bytes()).hexdigest()
        name = self.project + '-' + component
        command = ['docker', 'run', '-d', '--name', name, '--label', self.label, '--network', self.network,
                   '--network-alias', alias, '--memory', memory, '--cpus', cpus, '--env-file', str(env),
                   '-v', str(self.private) + ':/fixture:ro']
        if component == 'iam': command += ['-v', str(self.private / 'keys') + ':/app/data/keys']
        if component == 'ai': command += ['--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL']
        command += extra or []
        command += [self.image]
        if component != 'ai': command += ['--config=/fixture/runtime.json']
        self.run(command); self.applications[component] = name
        actual = json.loads(self.run(['docker', 'inspect', name]).stdout)[0]
        budget = dict(memory_bytes=actual['HostConfig']['Memory'], nano_cpus=actual['HostConfig']['NanoCpus'])
        require(budget == dict(memory_bytes=int(memory.removesuffix('m')) * 1024 * 1024, nano_cpus=int(float(cpus) * 1_000_000_000)), 'actual_runtime_budget_differs')
        self.report.setdefault('actual_runtime_budgets', {})[component] = budget
        return name

    def http(self, component, port, path):
        target = self.applications[component]
        require(re.fullmatch(r'/[a-z0-9_./-]+', path), 'fixed_probe_path_required')
        # The Go images lack curl; use the original AI Python image for an owned
        # network probe without modifying any application root filesystem.
        result = self.run(['docker', 'run', '--rm', '--label', self.label, '--network', self.network,
            '--entrypoint', PYTHON, self.images['ai'], '-c', "import urllib.request; print(urllib.request.urlopen('http://" + target + ':' + str(port) + path + "',timeout=2).read().decode())"], timeout=15, required=False)
        require(result.returncode == 0, 'owned_http_probe_not_ready')
        return result.stdout

    def ready(self, component, port, path, validator=None):
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            require(self.run(['docker', 'inspect', self.applications[component], '--format', '{{.State.Running}}']).stdout.strip() == 'true', 'actual_' + component.replace('-', '_') + '_exited')
            try:
                value = self.http(component, port, path)
                return validator(value) if validator else hashlib.sha256(value.encode()).hexdigest()
            except RuntimeError:
                time.sleep(1)
        raise RuntimeError('actual_' + component.replace('-', '_') + '_ready_budget_exceeded')

    def diagnostic(self, component, source):
        name = self.applications[component]
        result = self.run(['docker', 'logs', name], required=False)
        raw = result.stdout + result.stderr
        state = json.loads(self.run(['docker', 'inspect', name]).stdout)[0]['State']
        result = dict(private_log_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                      state={k: state[k] for k in ('Status', 'ExitCode', 'OOMKilled')})
        result['fixed_failure_signals'] = {key: token in raw.lower() for key, token in {
            'missing_file': 'no such file or directory', 'policy_read': 'cache policy',
            'permission_denied': 'permission denied', 'connection_refused': 'connection refused',
            'deadline': 'deadline exceeded', 'certificate_authority': 'unknown authority',
            'missing_route': 'route', 'invalid_configuration': 'invalid', 'panic': 'panic:'}.items()}
        if component != 'ai': result['source_markers'] = source_failure_markers(raw, source)
        return result


def main():
    import yaml
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('sources', 'candidate', 'qs_initializer', 'iam_initializer', 'report'):
        p.add_argument('--' + key.replace('_', '-'), type=Path, required=True)
    args = p.parse_args(); require(not args.report.exists(), 'new_report_required')
    repo = Path(__file__).resolve().parents[2]
    report = dict(schema='m3-five-actual-image-startup-trial/v1', passed=0, failed=0, skipped=0,
                  production=False, system_acceptance=False, combined_cutover_rehearsal_complete=False,
                  c1_cutover_barrier_exercised=False, cases={}, sources=SOURCES)
    f = FiveImageFixture(repo, report); run = f.run
    f.applications = {}; f.images = {}; f.private_dirs = {}
    def case(name): report['cases'][name] = True
    try:
        report['infra_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
        for name, sha in SOURCES.items():
            require(run(['git', 'rev-parse', 'HEAD'], cwd=args.sources / name).stdout.strip() == sha
                    and not run(['git', 'status', '--porcelain'], cwd=args.sources / name).stdout, 'exact_clean_source_required')
        candidates = {}
        for component, target, sha in [('iam', 'iam', IAM_SHA), ('api', 'qs-api', QS_SHA), ('collection', 'qs-collection', QS_SHA), ('worker', 'qs-worker', QS_SHA), ('ai', 'ai', AI_SHA)]:
            metadata = f.load(args.candidate / target, target, sha)
            f.images[component] = f.image; candidates[target] = report['candidate']
            private = f.directory / component; private.mkdir(mode=0o700); f.private_dirs[component] = private
            if component == 'api':
                tool = args.candidate / target / 'qs-migrate-offline'
                require(hashlib.sha256(tool.read_bytes()).hexdigest() == metadata['offline_tool_sha256'], 'original_companion_required')
                shutil.copyfile(tool, private / 'qs-migrate-offline'); (private / 'qs-migrate-offline').chmod(0o755)
        report['candidates'] = candidates; report.pop('candidate'); case('all_five_exact_archives_loaded')
        f.select('api'); f.dependencies(); f.mongo_dependencies()
        run(['docker', 'pull', 'redis:7-alpine'], timeout=300)
        run(['docker', 'run', '-d', '--name', f.project + '-redis', '--label', f.label, '--network', f.network, '--network-alias', 'redis',
             '--memory', '256m', '--cpus', '1', 'redis:7-alpine'])
        report['dependency_image_ids']['redis'] = run(['docker', 'image', 'inspect', 'redis:7-alpine', '--format', '{{.Id}}']).stdout.strip()
        # Resource types and the five exact accounts come from the current
        # reviewed manifest. No fixture superuser is used by an application.
        document = manifest(repo); accounts = {role: dict(username='owned-' + secrets.token_hex(8), password=secrets.token_hex(32)) for role in document['accounts']}
        report['resources'] = provision(f.project + '-broker-1', document, accounts)
        tls = f.directory / 'service-tls'; tls.mkdir(mode=0o700)
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=owned-service-ca',
             '-keyout', str(tls / 'service-ca.key'), '-out', str(tls / 'service-ca.crt')])
        for name, cn, aliases in [('iam-apiserver', 'iam-apiserver', ['iam-apiserver']), ('qs-apiserver', 'qs-apiserver.svc', ['qs-apiserver', 'qs-apiserver.svc']),
                                  ('qs-collection-server', 'qs-collection-server.svc', ['qs-collection-server.svc']), ('qs-worker', 'qs-worker.svc', ['qs-worker.svc']),
                                  ('ai', 'qs-ai.svc', ['ai', 'qs-ai.svc'])]: f.certificate(name, cn, aliases)
        mq_ca = f.private / 'mq-ca.crt'
        for component, private in f.private_dirs.items():
            if mq_ca != private / 'mq-ca.crt': shutil.copyfile(mq_ca, private / 'mq-ca.crt')
            identity = {'iam': 'iam-apiserver', 'api': 'qs-apiserver', 'collection': 'qs-collection-server', 'worker': 'qs-worker', 'ai': 'ai'}[component]
            for filename in ('service-ca.crt', identity + '.crt', identity + '.key'):
                shutil.copyfile(tls / filename, private / filename)
            write_private(private / 'routes.json', document)
            selected = {'iam': {'iam': 'm3-iam'}, 'ai': {'ai': 'm3-ai'}, 'api': {'qs': 'm3-qs-apiserver', 'mongo': 'm3-qs-mongo'},
                        'worker': {'worker': 'm3-qs-worker'}, 'collection': {}}[component]
            for name, role in selected.items(): write_private(private / (name + '-credentials.json'), accounts[role])
        # Prepare current QS schemas and original binding on independent facts.
        f.stage = 'original_current_qs_pair'; f.select('api')
        shutil.copyfile(args.qs_initializer, f.private / 'qs-pair-init'); (f.private / 'qs-pair-init').chmod(0o755); f.ownership(2000)
        qs_db = 'qs_m3_image_start_' + secrets.token_hex(6)
        report['qs_schema'] = f.prepare(qs_db, 'current'); case('original_current_qs_pair_prepared')
        env = dict(QS_OFFLINE_MYSQL_DSN=f'root:{f.password}@tcp(mysql:3306)/{qs_db}?parseTime=true', QS_OFFLINE_MONGO_URI='mongodb://mongo:27017/?replicaSet=image-proof')
        common = ['--mysql-database', qs_db, '--mongo-database', qs_db, '--timeout', '30s']
        for owner in ('qs.mysql', 'qs.mongo'):
            plan = '/fixture/' + owner + '.json'
            f.once('/fixture/qs-migrate-offline', common + ['--binding-action', 'preview', '--binding-plan', plan, '--binding-operation-id', 'owned-startup-trial',
                   '--binding-owner', owner, '--binding-store-id', 'isolated-' + owner.replace('.', '-') + '-primary', '--binding-writer-epoch', 'm3-1'], environment=env)
            digest = f.once('/usr/bin/sha256sum', [plan], network=False).split()[0]
            f.once('/fixture/qs-migrate-offline', common + ['--binding-action', 'apply', '--binding-plan', plan, '--binding-reviewed-sha256', digest, '--binding-writers-excluded'], environment=env)
            verified = json.loads(f.once('/fixture/qs-migrate-offline', common + ['--binding-action', 'verify', '--binding-plan', plan, '--binding-reviewed-sha256', digest], environment=env))
            require(verified['verified'] is True, 'original_binding_readback_required')
        case('original_qs_dual_binding_verified')
        f.ownership(os.getuid())
        f.stage = 'original_iam_schema_and_selection'; f.select('iam')
        iam_db = 'iam_m3_image_start_' + secrets.token_hex(6); f.sql('CREATE DATABASE `' + iam_db + '`;')
        shutil.copyfile(args.iam_initializer, f.private / 'iam-init'); (f.private / 'iam-init').chmod(0o755); f.ownership(2000)
        env = {k: os.environ[k] for k in ('GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT')}
        env['IAM_IMAGE_FIXTURE_DSN'] = f'root:{f.password}@tcp(mysql:3306)/{iam_db}?parseTime=true&multiStatements=true'
        report['iam_controlled_seed'] = seed_receipt(f.once('/fixture/iam-init', [], environment=env))
        cli_env = {'IAM_APISERVER_MYSQL_' + k: v for k, v in dict(HOST='mysql', PORT='3306', USERNAME='root', PASSWORD=f.password, DATABASE=iam_db, TLS_MODE='disabled').items()}
        for action in ('schema', 'select'):
            plan = '/fixture/' + action + '.json'
            f.once('/app/iam-maintenance', ['m3-messaging', '--action', action, '--store-id', 'isolated-iam-primary', '--writer-epoch', 'm3-1', '--export-plan', plan], environment=cli_env)
            digest = f.once('/usr/bin/sha256sum', [plan], network=False).split()[0]
            f.once('/app/iam-maintenance', ['m3-messaging', '--apply', '--writers-excluded', '--plan', plan, '--reviewed-sha256', digest], environment=cli_env)
        case('original_iam_schema45_and_binding_selected')
        f.ownership(os.getuid())
        f.stage = 'original_ai_schema_and_binding'; f.select('ai')
        ai_db = 'ai_m3_image_start_' + secrets.token_hex(6); f.sql('CREATE DATABASE `' + ai_db + '`;')
        ai_env = dict(QS_AI_ENVIRONMENT='production', QS_AI_DATABASE_TLS_MODE='DISABLED', HOME='/tmp',
                      QS_AI_DATABASE_URL=f'mysql+asyncmy://root:{f.password}@mysql:3306/{ai_db}', GRPC_DEFAULT_SSL_ROOTS_FILE_PATH='/fixture/mq-ca.crt')
        f.once(PYTHON, ['-m', 'alembic', 'upgrade', 'head'], environment=ai_env); f.ownership(10001)
        command = ['-m', 'qs_ai.maintenance.transaction_binding']
        f.once(PYTHON, command + ['--action', 'preview', '--plan', '/fixture/binding.json', '--operation-id', 'owned-startup-trial', '--store-id', 'isolated-ai-primary', '--writer-epoch', 'm3-1'], environment=ai_env)
        digest = f.once('/usr/bin/sha256sum', ['/fixture/binding.json'], network=False).split()[0]
        for action in ('apply', 'verify'):
            f.once(PYTHON, command + ['--action', action, '--plan', '/fixture/binding.json', '--reviewed-sha256', digest] + (['--writers-excluded'] if action == 'apply' else []), environment=ai_env)
        case('original_ai_schema43_and_binding_verified')
        # Existing original AI package generates keys; all identities and bytes
        # are frozen before application startup, with no model/provider calls.
        f.ownership(os.getuid()); write_private(f.private / 'credentials.json', accounts['m3-ai'])
        script = f.private / 'make_keys.py'; script.write_text(KEY_PROGRAM); script.chmod(0o600); f.ownership(10001)
        f.once(PYTHON, ['/fixture/make_keys.py'], network=False, environment={'HOME': '/tmp'}); f.ownership(os.getuid())
        for file in f.private.glob('*-public.json'): shutil.copyfile(file, f.private_dirs['api'] / file.name)
        for name in ('qs-sign-private.json', 'qs-recipient-private.json'):
            shutil.copyfile(f.private / name, f.private_dirs['api'] / name)
            (f.private / name).unlink()
        passwords = {name: secrets.token_hex(32) for name in ('iam', 'qs', 'ai')}
        for name, db in [('iam', iam_db), ('qs', qs_db), ('ai', ai_db)]:
            f.sql(f"CREATE USER '{name}_runtime'@'%' IDENTIFIED BY '{passwords[name]}'; GRANT SELECT,INSERT,UPDATE,DELETE ON `{db}`.* TO '{name}_runtime'@'%';")
        f.sql("SET GLOBAL log_output='TABLE'; SET GLOBAL general_log='ON';")
        # Mongo profiler is private and counts attempts; auth is not enabled in
        # this owned fixture, so this is not a production privilege proof.
        f.mongo('db.getSiblingDB(' + json.dumps(qs_db) + ').setProfilingLevel(2)')
        cfg = iam_configuration(yaml.safe_load((args.sources / 'iam/configs/apiserver.prod.yaml').read_text()), iam_db, passwords['iam'])
        cfg['grpc']['mtls'].update(**{'cert-file': '/fixture/iam-apiserver.crt', 'key-file': '/fixture/iam-apiserver.key', 'ca-file': '/fixture/service-ca.crt'})
        cfg['messaging']['credentials_file'] = '/fixture/iam-credentials.json'
        (f.private_dirs['iam'] / 'keys').mkdir(mode=0o700); write_private(f.private_dirs['iam'] / 'runtime.json', cfg)
        delegated = secrets.token_hex(32); report['configuration_sha256'] = {}
        for component, filename in [('api', 'apiserver.prod.yaml'), ('collection', 'collection-server.prod.yaml'), ('worker', 'worker.prod.yaml')]:
            cfg = qs_configuration(yaml.safe_load((args.sources / 'qs/configs' / filename).read_text()), component, qs_db, passwords['qs'], delegated)
            write_private(f.private_dirs[component] / 'runtime.json', cfg)
        for component in ('iam', 'api', 'collection', 'worker'):
            report['configuration_sha256'][component] = hashlib.sha256((f.private_dirs[component] / 'runtime.json').read_bytes()).hexdigest()
        for component in f.private_dirs:
            f.select(component); f.ownership(10001 if component == 'ai' else 2000)
        f.stage = 'actual_iam_with_mtls_start'; f.start('iam', alias='iam-apiserver', memory='512m', cpus='1')
        f.ready('iam', 9080, '/healthz'); report['iam_metrics'] = f.ready('iam', 9080, '/metrics', protocol_metrics); case('actual_iam_ready_and_paused_checker_live')
        f.stage = 'actual_readonly_ai_start'
        msg = ai_messaging()
        ai_env.update(QS_AI_DATABASE_URL=f'mysql+asyncmy://ai_runtime:{passwords["ai"]}@mysql:3306/{ai_db}',
            QS_AI_MESSAGING=json.dumps(msg), QS_AI_GRPC=json.dumps(dict(bind_address='0.0.0.0:50061', access_address='qs-apiserver:9090',
                ca_file='/fixture/service-ca.crt', cert_file='/fixture/ai.crt', key_file='/fixture/ai.key')),
            QS_AI_GENERATION__ENABLED='true', QS_AI_EVALUATION__ENABLED='true', QS_AI_DEEPSEEK_API_KEY='owned-unused-fixture-key', QS_AI_ZHIPU_API_KEY='owned-unused-fixture-key')
        f.start('ai', alias='ai', memory='768m', cpus='0.75', environment=ai_env)
        f.ready('ai', 8000, '/readyz'); report['ai_metrics'] = f.ready('ai', 8000, '/metrics', ai_metrics); case('actual_readonly_ai_ready_and_paused_checker_live')
        f.stage = 'actual_qs_api_start'; f.start('api', alias='qs-apiserver', memory='1024m', cpus='2')
        f.ready('api', 8080, '/healthz'); report['qs_metrics'] = f.ready('api', 8080, '/metrics', qs_metrics); case('actual_qs_api_with_iam_ai_and_both_paused_owners')
        f.stage = 'actual_collection_start'; f.start('collection', alias='qs-collection', memory='320m', cpus='1')
        f.ready('collection', 8080, '/healthz'); case('actual_collection_with_required_iam_and_api')
        f.stage = 'actual_three_workers_start'
        for index in range(1, 4):
            component = 'worker' + str(index); f.images[component] = f.images['worker']; f.private_dirs[component] = f.private_dirs['worker']
            f.start(component, alias=component, memory='768m', cpus='1')
            f.ready(component, 9092, '/healthz'); case('actual_' + component + '_ready_original_concurrency48')
        f.stage = 'actual_five_image_shutdown'; report['processes'] = {}
        for component in ('worker3', 'worker2', 'worker1', 'collection', 'api', 'ai', 'iam'):
            timeout = 210 if component == 'ai' else 60
            run(['docker', 'stop', '--time', str(timeout), f.applications[component]], timeout=timeout + 15)
            source = args.sources / ('ai' if component == 'ai' else 'iam' if component == 'iam' else 'qs')
            result = f.diagnostic(component, source); report['processes'][component] = result
            require(result['state'] == dict(Status='exited', ExitCode=0, OOMKilled=False), 'actual_' + component + '_shutdown_failed')
        case('all_seven_actual_processes_shutdown_exit_zero')
        ddl = f.sql("SELECT COUNT(*) FROM mysql.general_log WHERE user_host REGEXP '^(iam|qs|ai)_runtime' AND command_type='Query' AND UPPER(argument) REGEXP '^[[:space:]]*(CREATE|ALTER|DROP|TRUNCATE|RENAME)[[:space:]]';")
        report['mysql_runtime_ddl_attempts'] = int(ddl)
        mongo_ddl = f.mongo('print(db.getSiblingDB(' + json.dumps(qs_db) + ').system.profile.countDocuments({$or:["create","createIndexes","drop","dropDatabase","collMod","dropIndexes","renameCollection"].map(k=>({["command."+k]:{$exists:true}}))}))')
        report['mongo_runtime_ddl_attempts'] = int(mongo_ddl)
        require(ddl == mongo_ddl == '0', 'startup_shutdown_ddl_attempted'); case('actual_all_runtime_start_shutdown_no_ddl_attempts')
    except Exception as error:
        report.update(failed=1, failure_stage=f.stage, failure_kind=type(error).__name__)
        if re.fullmatch(r'[a-z][a-z0-9_]{1,100}', str(error)): report['failure_reason'] = str(error)
        report['processes'] = {}
        for component in f.applications:
            source = args.sources / ('ai' if component == 'ai' else 'iam' if component == 'iam' else 'qs')
            report['processes'][component] = f.diagnostic(component, source)
    finally:
        report['passed'] = len(report['cases'])
        try: f.cleanup()
        except Exception: report['failed'] = 1; report.setdefault('failure_stage', 'owned_cleanup')
        report['sources_unchanged'] = all(not run(['git', 'status', '--porcelain'], cwd=args.sources / name).stdout for name in SOURCES)
        if not report['sources_unchanged']: report['failed'] = 1
        write_private(args.report, report)
    return int(report['failed'] != 0)


if __name__ == '__main__': raise SystemExit(main())
