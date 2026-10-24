#!/usr/bin/env python3
"""CI-only 5.5.1 native recheck feasibility. No production recovery authority."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile
import time

from audit_transaction_limit import export, write_private
from render import render
from routes import consumer_group_v2
from v2_acceptance import setup
from managed_recovery_acceptance import accept as managed_accept, fixture_manifest as managed_manifest

SDK_SHA = '04757bd3212ca961d8eaec22ecd3560101111e18'
PARAMETERS = {'transactionTimeOut': 6000, 'transactionCheckInterval': 5000,
              'transactionCheckMax': 24, 'fileReservedTime': 48}


def require(value, stage):
    if not value:
        raise RuntimeError(stage)


def ci_guard(environment):
    require(environment.get('GITHUB_ACTIONS') == 'true'
            and environment.get('RUNNER_OS') == 'Linux'
            and environment.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'github_hosted_fixture_required')
    require(not environment.get('DOCKER_HOST') and not environment.get('DOCKER_CONTEXT'),
            'external_docker_context_refused')


def frame(raw, prefix):
    lines = [line[len(prefix):] for line in raw.splitlines() if line.startswith(prefix)]
    require(len(lines) == 1, 'single_private_result_required')
    result = json.loads(lines[0])
    require(isinstance(result, dict), 'private_result_shape')
    return result


def positive_admin_reply(operation, raw):
    # Pinned UpdateBrokerConfigSubCommand uses a comma, unlike UpdateTopic.
    phrase = 'update broker config success, ' if operation == 'updateBrokerConfig' else ' success.'
    return phrase in raw


def authoritative_snapshot(raw):
    fields = raw.split('\t')
    require(len(fields) == 6 and all(len(s) == 64 and all(c in '0123456789abcdefABCDEF' for c in s)
            for s in fields[:3]), 'exact_primary_witness_required')
    require(fields[3] in ('prepared', 'committed', 'aborted')
            and fields[4] in ('prepared', 'committed', 'aborted')
            and fields[5] in ('not_attempted', 'unknown', 'commit_confirmed', 'rollback_confirmed'),
            'primary_witness_state_shape')
    return dict(reference_sha256=fields[0].lower(), wire_sha256=fields[1].lower(),
                unique_id_sha256=fields[2].lower(), execution_state=fields[3],
                witness_state=fields[4], final_outcome=fields[5])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--managed-tool', type=Path, help='fixed published-module CLI; owned isolated fixture only')
    parser.add_argument('--governance-faults',action='store_true',help='actual MySQL COMMIT before/after reply loss for managed CLI only')
    parser.add_argument('--iam-host',type=Path,help='actual fixed IAM original writer, owned fixture only')
    parser.add_argument('--host-observer',type=Path,help='CI-only actual-host consumer compiled against the same published SDK')
    parser.add_argument('--terminal',choices=('commit','rollback'),default='commit',help='terminal SDK evidence; rollback uses durable abort fence, no business root')
    args = parser.parse_args()
    ci_guard(os.environ)  # Never construct a client or invoke Docker on a workstation.
    require(not args.governance_faults or args.managed_tool is not None,'managed_cli_required_for_governance_faults')
    require(not args.iam_host or (args.managed_tool and args.host_observer and not args.governance_faults),'separate_actual_iam_managed_profile_required')
    require(args.terminal=='commit' or (args.managed_tool and not args.iam_host and not args.governance_faults),'separate_compiled_rollback_profile_required')
    require(not args.report.exists() and not args.report.is_symlink(), 'report_already_exists')
    module = importlib.util.spec_from_file_location('_native_fixture', Path(__file__).with_name('ci-transactions.py'))
    common = importlib.util.module_from_spec(module)
    module.loader.exec_module(common)
    run = common.run
    context = json.loads(run(['docker', 'context', 'inspect']).stdout)
    require(len(context) == 1 and context[0]['Endpoints']['docker']['Host'] == 'unix:///var/run/docker.sock',
            'local_ci_daemon_required')
    sdk = args.sdk.resolve()
    require(run(['git', 'rev-parse', 'HEAD'], cwd=sdk).stdout.strip() == SDK_SHA
            and not run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=sdk).stdout,
            'fixed_clean_sdk_required')
    repo = Path(__file__).resolve().parents[2]
    directory = Path(tempfile.mkdtemp(prefix='rocketmq-m2-')); directory.chmod(0o700)
    project = 'rocketmq-m2-' + secrets.token_hex(6)
    report = dict(schema='m3-native-recheck-feasibility/v0', infra_sha=run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip(),
                  sdk_sha=SDK_SHA, passed=0, failed=0, skipped=0, failure=None, cases={}, proof={}, cleanup={},
                  limits=['Isolated fixed SDK source probe, not published-artifact or original host acceptance',
                          'Original producer exits23 after real local COMMIT; not SIGKILL or packet loss',
                          'Native internal copy may redeliver; no exactly-once or indefinite recovery promise',
                          'No production/system/provider or original business-host acceptance; managed mode tests owned original SDK DB/governance'])
    proof, cases, probes = report['proof'], report['cases'], []
    proof['harness_sha256'] = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__).resolve(), repo/'scripts/rocketmq/probes/native-recheck/NativeHalfRecheck.java',
                  repo/'scripts/rocketmq/probes/native-recheck/NativeHalfWindowTest.java')}
    compose = None; image = None; broker = project+'-broker-1'; mysql = project+'-mysql-1'
    before = {}; stage = 'fixture_preflight'; before_parameters = None
    def passed(name):
        require(name not in cases, 'duplicate_case')
        cases[name] = 'pass'; report['passed'] += 1
    def ids(kind):
        argv = ['docker', 'ps', '-aq'] if kind == 'containers' else ['docker', 'network', 'ls', '-q']
        return set(run(argv).stdout.split())
    def admin(operation, *params, success=False):
        raw = run(['docker', 'exec', broker, 'java', '-Xms32m', '-Xmx128m', '-XX:MaxDirectMemorySize=32m',
                   '-cp', '/opt/rocketmq/conf:/opt/rocketmq/lib/*', 'org.apache.rocketmq.tools.command.MQAdminStartup',
                   operation, '-b', '127.0.0.1:10911', *params], timeout=45).stdout
        require(not success or positive_admin_reply(operation, raw), 'admin_positive_reply_required')
        return raw
    original_database='txprobe'
    def sql(query):
        return run(['docker', 'exec', '-i', mysql, 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B "$1"','sh',original_database], stdin=query).stdout.strip()
    try:
        before = {kind: ids(kind) for kind in ('containers', 'networks')}
        image = run(['docker', 'image', 'inspect', args.image, '--format', '{{.Id}}']).stdout.strip()
        require(run(['docker', 'image', 'inspect', image, '--format', '{{index .Config.Labels "org.opencontainers.image.version"}}']).stdout.strip() == '5.5.1', 'fixed_broker_version_required')
        run(['docker', 'pull', 'mysql:8.0.36'], timeout=300)
        mysql_image = run(['docker', 'image', 'inspect', 'mysql:8.0.36', '--format', '{{.Id}}']).stdout.strip()
        proof['images'] = dict(broker=image, mysql=mysql_image)
        config, data = directory/'config', directory/'data'
        config.mkdir(); data.mkdir(); (config/'tls').mkdir()
        ports = set()
        while len(ports) < 3: ports.add(common.port())
        grpc_port, metrics_port, mysql_port = sorted(ports)
        accounts = {name: dict(username='m2-'+name, password=secrets.token_hex(32))
                    for name in ('admin', 'inner', 'owner-a', 'owner-b', 'observer')}
        password = secrets.token_hex(32)
        render(accounts, config, '127.0.0.1', repo/'components/rocketmq')
        with (config/'broker.conf').open('a') as stream:
            stream.write(''.join(f'{key}={value}\n' for key, value in PARAMETERS.items()))
        proxy = json.loads((config/'proxy.json').read_text()); proxy['grpcServerPort'] = grpc_port
        (config/'proxy.json').write_text(json.dumps(proxy))
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-subj', '/CN=rocketmq-m2-isolated',
             '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost,DNS:nameserver,DNS:broker',
             '-keyout', str(config/'tls/server.key'), '-out', str(config/'tls/server.crt')])
        ca = directory/'ca.crt'; shutil.copyfile(config/'tls/server.crt', ca); ca.chmod(0o600)
        run(['docker', 'run', '--rm', '--user', '0', '--entrypoint', 'bash', '-v', str(config)+':/config',
             '-v', str(data)+':/data', image, '-c', 'mkdir -p /data/store /data/auth /data/logs /data/nameserver-logs; '
             'chown -R 3000:3000 /data /config; chmod 750 /config /config/tls; '
             'chmod 640 /config/broker.conf /config/proxy.json /config/tools.yml /config/tls/server.key'])
        environment = dict(os.environ, ROCKETMQ_IMAGE=image, ROCKETMQ_BIND_IP='127.0.0.1',
            ROCKETMQ_GRPC_PORT=str(grpc_port), ROCKETMQ_METRICS_PORT=str(metrics_port),
            ROCKETMQ_DATA_ROOT=str(data), ROCKETMQ_CONFIG_ROOT=str(config))
        spec = json.loads(run(['docker', 'compose', '-f', str(repo/'components/rocketmq/docker-compose.yml'),
                              'config', '--format', 'json'], env=environment).stdout)
        spec.pop('name', None)
        for network in spec['networks'].values():
            require(not network.get('external'), 'external_fixture_network_refused'); network.pop('name', None)
        for service in spec['services'].values(): service['restart'] = 'no'
        spec['services']['broker']['ports'][0]['target'] = grpc_port
        spec['services']['broker']['healthcheck']['test'][-1] = f'exec 3<>/dev/tcp/127.0.0.1/{grpc_port}'
        spec['services']['mysql'] = dict(image=mysql_image, environment=dict(MYSQL_ROOT_PASSWORD=password,
            MYSQL_DATABASE='txprobe', MYSQL_USER='txprobe', MYSQL_PASSWORD=password),
            ports=[f'127.0.0.1:{mysql_port}:3306'], networks=['rocketmq'], mem_limit='512m', cpus=1,
            tmpfs=['/var/lib/mysql'], healthcheck=dict(test=['CMD-SHELL', 'MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysql -uroot -e "SELECT 1"'],
                                                     interval='3s', timeout='3s', retries=40))
        compose_file = directory/'compose.json'; write_private(compose_file, spec)
        compose = ['docker', 'compose', '-p', project, '-f', str(compose_file)]
        stage = 'owned_dependencies_start'
        run(compose+['up', '-d', '--wait', '--wait-timeout', '180'], timeout=240)
        before_parameters = common.broker_parameters(admin('getBrokerConfig'))
        require(before_parameters == PARAMETERS, 'actual_parameters_required')
        proof['parameters_before'] = before_parameters
        stage='typed_route_setup'
        manifest, proof['routing'] = setup(repo, sdk, broker, project, accounts, directory, admin, run, passed,
            fixture_manifest=managed_manifest(repo,iam=bool(args.iam_host)) if args.managed_tool else None)
        revision = 'm3-1' if args.managed_tool else 'sdk-v2'
        route = next(r for r in manifest['routes'] if r['owner']=='iam.mysql' and r['route_revision']==revision and r['message_type']=='TRANSACTION')
        binary = directory/'sdk-go-probe'
        stage = 'fixed_source_compile'
        run(['go', 'build', '-race', '-mod=readonly', '-o', str(binary), './transport/rocketmq/internal/sdkprobe'], cwd=sdk,
            env=dict(os.environ, GOWORK='off', GOTOOLCHAIN='local'), timeout=300)
        proof['go_binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
        stage = 'java_compile'
        java_source = repo/'scripts/rocketmq/probes/native-recheck'
        libraries, classes = directory/'java-lib', directory/'java-classes'; libraries.mkdir(); classes.mkdir()
        run(['docker', 'cp', broker+':/opt/rocketmq/lib/.', str(libraries)], timeout=60)
        run(['javac', '--release', '17', '-g:none', '-cp', str(libraries/'*'), '-d', str(classes),
             str(java_source/'NativeHalfRecheck.java'), str(java_source/'NativeHalfWindowTest.java'), str(java_source/'NativeHalfManaged.java')])
        proof['java_compiler'] = run(['javac', '-version']).stdout.strip()
        container_java = '/tmp/native-recheck-'+secrets.token_hex(8)
        run(['docker', 'exec', broker, 'mkdir', '-m', '700', container_java])
        # javac inherits the fixture's umask077. Only these public bytecode files
        # are copied; make them readable by the fixed nonroot Broker JVM.
        stage = 'owned_java_classes_install'
        for public_class in classes.glob('*.class'): public_class.chmod(0o644)
        classes.chmod(0o755)
        run(['docker', 'cp', str(classes)+'/.', broker+':'+container_java])
        run(['docker', 'exec', '--user', '0', broker, 'chown', '-R', '3000:3000', container_java])
        run(['docker', 'exec', broker, 'chmod', '700', container_java])
        java = ['docker', 'exec', '-i', '-e', 'GITHUB_ACTIONS=true', '-e', 'M3_NATIVE_RECHECK_PROJECT='+project,
                broker, 'java', '-Xms32m', '-Xmx128m', '-XX:MaxDirectMemorySize=32m',
                '-Djava.io.tmpdir='+container_java, '-Drocketmq.client.logRoot='+container_java+'/logs',
                '-cp', '/opt/rocketmq/conf:/opt/rocketmq/lib/*:'+container_java]
        stage = 'pure_java_finite_window'
        window_process = run(java+['NativeHalfWindowTest'], required=False)
        proof['pure_java_exit_code'] = window_process.returncode
        if window_process.returncode:
            proof['pure_java_failure_category'] = ('main_class_unavailable' if 'Could not find or load main class' in window_process.stderr
                else 'java_policy_or_launch_failure')
            raise RuntimeError('pure_java_failed')
        window = frame(window_process.stdout, 'M3_NATIVE_WINDOW ')
        require(window == dict(passed=11, failed=0, skipped=0, network_started=False), 'finite_window_policy_failed')
        proof['finite_window_pure'] = window; passed('eleven_pure_finite_window_and_physical_bounds')
        def start(mode, identity=''):
            role = 'observer' if mode == 'consume' else 'owner-a'; account = accounts[role]
            path = directory/('client-'+secrets.token_hex(8)+'.json')
            write_private(path, dict(endpoint=f'127.0.0.1:{grpc_port}', accesskey=account['username'], secretkey=account['password'],
                ca=str(ca), topic=route['physical_topic'], group=consumer_group_v2(route['topic'], route['subscription']),
                owner='iam.mysql', subscription='sdk-mysql-observer', inputs=[{k:v for k,v in route.items() if k!='id'}],
                owner_routes=[dict(topic=r['topic'], physical_topic=r['physical_topic'], route_revision=r['route_revision'])
                              for r in manifest['routes'] if r['owner']=='iam.mysql' and r['message_type']=='TRANSACTION'],
                route_revision=revision, storage='mysql', branches=1, lease_millis=3_600_000,
                dsn=f'txprobe:{password}@tcp(127.0.0.1:{mysql_port})/txprobe?timeout=1s&readTimeout=5s&writeTimeout=5s'))
            argv=([str(args.host_observer.resolve()),'--config',str(path),'--config-sha',hashlib.sha256(path.read_bytes()).hexdigest()]
                if args.iam_host and mode=='consume' else [str(binary), '--config', str(path), '--mode', mode, '--id', identity])
            probe = common.Probe(argv, directory,
                                 dict(os.environ, GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=str(ca)))
            probes.append(probe); return probe
        if not args.iam_host:
            install = start('init'); install.wait('installed'); install.finish()
        stage='original_observer_start'
        consumer = start('consume'); consumer.wait('ready')
        identity = 'native-recheck-'+secrets.token_hex(12)
        host=None;original=None
        if args.terminal=='rollback':
            report['limits']=['Fixed SDK source producer returns LocalAborted after genuine half reaches native limit; actual durable abort fence, no business row',
                'Original sender drains normally; no process crash, business root rollback or whole-host acceptance claim',
                'Compiled published SDK recheck performs actual Rollback RPC, preserves first audit; bounded three-second consumer observation',
                'Synthetic reviewers, no production/system authorization']
        if args.iam_host:
            report['limits']=['Actual IAM planned writer and owned original GORM root, not whole API or system',
                'Original owner drains during real Broker network disconnection; no SIGKILL claim',
                'Native internal copy may redeliver; no exactly-once or indefinite recovery promise',
                'Synthetic reviewers and isolated owned resources; no production authorization']
        if args.iam_host:
            stage='actual_iam_original_half'
            from iam_recovery_acceptance import IAMHost,metadata
            host=IAMHost(source=args.iam_host,directory=directory,project=project,route=route,grpc_port=grpc_port,mysql_port=mysql_port,
                password=password,ca=ca,account=accounts['owner-a'],run=run,common=common,probes=probes,proof=proof)
            original=metadata(host.wait('half.json'));identity=original['message_id'];original_database=original['database']
        original_operation=original['operation_id'] if original else 'op-'+identity
        def snapshot():
            return authoritative_snapshot(sql("SELECT SHA2(w.reference,256), JSON_UNQUOTE(JSON_EXTRACT(CONVERT(w.reference USING utf8mb4),'$.wire_hash')), SHA2(w.broker_message_id,256),e.state,w.state,w.final_outcome FROM rm_tx_execution e JOIN rm_tx_witness w ON w.execution_key=e.execution_key WHERE e.owner='iam.mysql' AND e.operation_id='"+original_operation+"';"))
        def counts():
            return sql("SELECT ("+(original["business_count_sql"] if original else "SELECT COUNT(*) FROM sdk_business")+"),(SELECT COUNT(*) FROM rm_tx_request),(SELECT COUNT(*) FROM rm_tx_execution),(SELECT COUNT(*) FROM rm_tx_witness);")
        stage = 'native_limit_of_genuinely_prepared_message'
        admin('updateBrokerConfig', '-k', 'transactionCheckMax', '-v', '2', success=True)
        proof['parameters_fault'] = common.broker_parameters(admin('getBrokerConfig'))
        require(proof['parameters_fault'] == dict(PARAMETERS, transactionCheckMax=2), 'bounded_fault_parameters_required')
        producer=None
        if not host:
            producer = start('send' if args.terminal=='rollback' else 'crash-committed', identity); producer.wait('half', identity)
        else:
            network=run(['docker','inspect','--format','{{range $name,$config := .NetworkSettings.Networks}}{{$name}}{{end}}',broker]).stdout.strip()
            require(network.startswith(project+'_') and json.loads(run(['docker','network','inspect',network]).stdout)[0]['Labels']['com.docker.compose.project']==project,'owned_broker_network_required')
            run(['docker','network','disconnect',network,broker])
            proof['iam_broker_network_disconnected']=True
            host.signal('commit');require(host.wait('closed.json',35)==dict(original_root_committed=True,owner_stopped=True,business_executions=1),'original_root_not_closed')
            run(['docker','network','connect','--alias','broker',network,broker])
            proof['iam_broker_network_reconnected_after_owner_stop']=True
        prepared = snapshot()
        wanted_state='committed' if host else 'prepared'
        wanted_counts='1\t1\t1\t1' if host else '0\t1\t1\t1'
        require(prepared['execution_state'] == prepared['witness_state'] == wanted_state and counts() == wanted_counts, 'prepared_original_root_required')
        index_path = directory/'native-index.json'; index = None
        deadline = time.monotonic()+110
        while time.monotonic() < deadline:
            try:
                index = export(broker, project, identity, index_path); break
            except RuntimeError: time.sleep(2)
        require(index is not None and len(index['records'])==1 and not index['truncated_possible'], 'exact_native_limit_index_required')
        require(stat.S_IMODE(index_path.stat().st_mode)==0o600, 'private_index_mode')
        proof['native_index_sha256'] = hashlib.sha256(index_path.read_bytes()).hexdigest()
        proof['native_index_records'] = 1; passed('actual_iam_unconfirmed_original_commit_reaches_native_check_limit' if host else 'genuine_prepared_unknown_reaches_native_check_limit')
        for key, value in before_parameters.items(): admin('updateBrokerConfig', '-k', key, '-v', str(value), success=True)
        proof['parameters_restored_before_recovery'] = common.broker_parameters(admin('getBrokerConfig'))
        require(proof['parameters_restored_before_recovery'] == before_parameters, 'parameters_not_restored')
        stage = 'original_commit_then_real_process_exit'
        if producer:
            producer.send('rollback' if args.terminal=='rollback' else 'commit'); producer.finish(expected=0 if args.terminal=='rollback' else 23)
        if host:
            shutil.copyfile(index_path,host.control/'native-index.json');(host.control/'native-index.json').chmod(0o600)
            host.signal('record-notice');require(host.wait('notice.json',10)==dict(exact_original_index_recorded=True),'original_host_native_import_required')
        committed = snapshot()
        expected_state='aborted' if args.terminal=='rollback' else 'committed'
        expected_counts='0\t1\t1\t1' if args.terminal=='rollback' else '1\t1\t1\t1'
        require(committed['execution_state']==committed['witness_state']==expected_state
                and (args.terminal=='rollback' or committed['final_outcome']!='commit_confirmed') and counts()==expected_counts, 'original_terminal_evidence_required')
        require(all(committed[k]==prepared[k] for k in ('reference_sha256','wire_sha256','unique_id_sha256')), 'original_frozen_identity_changed')
        proof['original_exit_code'] = None if host else 0 if args.terminal=='rollback' else 23
        passed('actual_iam_root_committed_during_broker_disconnect_and_owner_stopped' if host else 'real_prepared_execution_durably_aborted_without_business_fact' if args.terminal=='rollback' else 'real_original_root_committed_then_process_exited_before_final_rpc')
        if args.managed_tool:
            stage = 'compiled_managed_original_primary_recovery'
            managed_accept(repo=repo,binary=args.managed_tool.resolve(),broker=broker,project=project,directory=directory,
                manifest=manifest,route=route,account=accounts['owner-a'],grpc_port=grpc_port,mysql_port=mysql_port,password=password,
                ca=ca,java=java,identity=identity,index_path=index_path,index=index,sql=sql,run=run,consumer=consumer,passed=passed,proof=proof,governance_faults=args.governance_faults,original=original,terminal=args.terminal)
        else:
            recovery = start('recover', identity); recovery.wait('ready', identity)
            recovery.send('seal'); recovery.wait('sealed', '', 'admission_stopped_checker_alive')
            time.sleep(2); recovery.drain(); consumer.drain()
            require(not any(e.get('event') in ('checked_reference', 'recovery_recorded', 'half') for e in recovery.events)
                    and not any(e.get('event')=='received' and e.get('id')==identity for e in consumer.events), 'native_exhaustion_not_established')
            passed('new_process_admission_stopped_checker_alive_no_automatic_recovery')
            request = dict(mode='inspect', source_topic='TRANS_CHECK_MAX_TIME_TOPIC',
                commitlog_offset=index['records'][0]['commitlog_offset'], queue_id=index['records'][0]['queue_id'],
                queue_offset=index['records'][0]['queue_offset'], expected_real_topic=route['physical_topic'],
                expected_owner='iam.mysql', expected_route_revision=revision, expected_retention_hours=48,
                expected_reference_sha256=committed['reference_sha256'], expected_wire_sha256=committed['wire_sha256'],
                expected_unique_id_sha256=committed['unique_id_sha256'])
            def invoke(value, negative=False):
                result = run(java+['NativeHalfRecheck'], stdin=json.dumps(value), required=False, timeout=45)
                safe = frame(result.stdout, 'M3_NATIVE_RECHECK ')
                require(safe.get('admin_shutdown_returned') is True and safe.get('body_exported') is False, 'native_private_shutdown_required')
                if negative:
                    require(result.returncode!=0 and safe.get('outcome')=='NotAttempted' and safe.get('stage')=='frozen_identity', 'wrong_identity_not_refused')
                elif result.returncode:
                    proof['native_operation_failure'] = safe
                    raise RuntimeError('native_private_operation_failed')
                return safe
            stage = 'exact_native_inspection'
            proof['inspection'] = invoke(request); passed('exact_native_body_reference_identity_and_finite_window_verified')
            for field, wrong in (('expected_reference_sha256','0'*64), ('expected_wire_sha256','0'*64), ('expected_owner','qs.mysql')):
                invoke(dict(request, **{field:wrong}), negative=True); passed('native_refuses_'+field)
            require(snapshot()==committed and counts()=='1\t1\t1\t1', 'inspection_mutated_primary')
            stage = 'explicit_native_recheck'
            proof['native_recheck'] = invoke(dict(request, mode='resume'))
            require(proof['native_recheck']['outcome']=='RecheckEnqueued', 'native_recheck_enqueue_not_confirmed')
            passed('explicit_original_native_record_recheck_enqueued_not_committed_by_admin')
            stage = 'real_new_checker_rpc_and_audit'
            recovery.wait('checked_reference', identity, 'commit', timeout=100)
            recovery.wait('recovery_recorded', identity, 'commit_confirmed', timeout=100)
            consumer.wait('received', identity, timeout=100)
            final = snapshot()
            require(final == dict(committed, final_outcome='commit_confirmed') and counts()=='1\t1\t1\t1', 'exact_final_receipt_or_original_counts_changed')
            passed('new_checker_reads_original_committed_witness_actual_rpc_positive_audit')
            passed('consumer_receives_original_message_identity_without_new_execution')
            after_index = export(broker, project, identity, directory/'native-index-after.json')
            require(after_index['records']==index['records'] and hashlib.sha256(index_path.read_bytes()).hexdigest()==proof['native_index_sha256'], 'original_native_index_changed')
            passed('raw_native_index_retained_unchanged')
            recovery.send('stop'); recovery.wait('closed', identity, 'drained'); recovery.finish()
            metrics = [json.loads(e['decision']) for e in recovery.events if e.get('event')=='metrics']
            require(metrics and metrics[-1]['RecoveryAuditRecorded']>=1 and metrics[-1]['RecoveryAuditErrors']==0
                    and not any(e.get('event')=='half' for e in recovery.events), 'real_recovery_stats_required')
            proof['recovery_metrics'] = metrics[-1]; proof['original_counts'] = dict(business=1, requests=1, executions=1, witnesses=1)
            proof['exact_witness'] = final; passed('replacement_has_zero_new_half_and_actual_resources_drained')
        consumer.send('stop'); consumer.wait('closed'); consumer.finish()
        if host:
            host.finish();passed('actual_iam_original_primary_resolved_and_paused_replacement_keeps_checker')
            remaining=run(['docker','exec','-i',mysql,'sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'],stdin="SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name LIKE 'iam_m3_broker_test_%';").stdout.strip()
            require(remaining=='0','owned_original_host_database_cleanup_required')
            proof['owned_iam_database_removed']=True
        require(not run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=sdk).stdout, 'sdk_source_changed')
        proof['sdk_tracked_sources_clean'] = True
        require(report['passed']==((15 if host or args.terminal=='rollback' else 16 if args.governance_faults else 14) if args.managed_tool else 17), 'complete_nonempty_native_matrix_required')
    except Exception:
        report['failed'] = 1; report['failure'] = stage
    finally:
        if before_parameters:
            try:
                for key,value in before_parameters.items(): admin('updateBrokerConfig', '-k', key, '-v', str(value), success=True)
                report['cleanup']['broker_parameters_restored'] = common.broker_parameters(admin('getBrokerConfig'))==before_parameters
            except Exception: report['cleanup']['broker_parameters_restored'] = False
        drained = []
        for probe in probes:
            try: drained.append(probe.close())
            except Exception: drained.append(False)
        report['cleanup']['probe_process_groups_drained'] = all(drained)
        if compose:
            report['cleanup']['compose_down_succeeded'] = run(compose+['down','-v','--remove-orphans'], required=False, timeout=120).returncode==0
            report['cleanup']['project_containers_remaining'] = bool(run(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project]).stdout.strip())
            report['cleanup']['project_networks_remaining'] = bool(run(['docker','network','ls','-q','--filter','label=com.docker.compose.project='+project]).stdout.strip())
        else: report['cleanup']['compose_not_started'] = True
        for kind, original in before.items():
            report['cleanup']['existing_'+kind+'_unchanged'] = original == ids(kind)
        try:
            require(directory.parent==Path(tempfile.gettempdir()) and directory.name.startswith('rocketmq-m2-'), 'owned_directory_guard')
            if image:
                run(['docker','run','--rm','--user','0','--entrypoint','chown','-v',str(directory)+':/owned',image,'-R',f'{os.getuid()}:{os.getgid()}','/owned'], timeout=45)
            shutil.rmtree(directory)
            report['cleanup']['private_fixture_directory_removed'] = not directory.exists()
        except Exception: report['cleanup']['private_fixture_directory_removed'] = False
        expected = dict(broker_parameters_restored=True, probe_process_groups_drained=True, compose_down_succeeded=True,
                        project_containers_remaining=False, project_networks_remaining=False, existing_containers_unchanged=True,
                        existing_networks_unchanged=True, private_fixture_directory_removed=True)
        if report['cleanup'] != expected:
            report['failed'] = 1; report['failure'] = report['failure'] or 'owned_fixture_cleanup'
        write_private(args.report, report)
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
