"""Drive the same AI SQLAlchemy root and native Broker limit in an owned stack."""
import hashlib
import json
import json
import os
from pathlib import Path
import re
import time
from xml.etree import ElementTree

from audit_transaction_limit import TOPIC, export
from provision_v2 import Admin


def sys_index_context(run, broker, original_key):
    """Summarize owned Broker evidence without publishing keys, records or raw logs."""
    def observe(*command):
        try:
            return run(['docker', 'exec', broker, *command], required=False, timeout=12)
        except RuntimeError:
            return None

    logs = observe('sh', '-ec',
                   'set -- $(find /home/rocketmq/logs/rocketmqlogs -maxdepth 3 -type f -name transaction.log); '
                   'test "$#" -eq 1; tail -c 524288 "$1"')
    context = {'transaction_log': {'available': logs is not None and logs.returncode == 0}}
    if context['transaction_log']['available']:
        lines = logs.stdout.splitlines()
        patterns = {
            'checks': 'Check transaction. real_topic=',
            'discarded': 'so discard it by moving it to system topic TRANS_CHECK_MAXTIME_TOPIC',
            'stored': 'Put checked-too-many-time half message to TRANS_CHECK_MAXTIME_TOPIC OK.',
            'store_failed': 'Put checked-too-many-time half message to TRANS_CHECK_MAXTIME_TOPIC failed',
            'store_exception': 'Put checked-too-many-time message to TRANS_CHECK_MAXTIME_TOPIC error.',
        }
        key_pattern = re.compile(r'(?<![A-Za-z0-9_.:-])' + re.escape(original_key) + r'(?![A-Za-z0-9_.:-])')
        context['transaction_log'].update(
            bytes=len(logs.stdout.encode()),
            counts={name: sum(marker in line for line in lines) for name, marker in patterns.items()},
            original_key_counts={name: sum(marker in line and bool(key_pattern.search(line)) for line in lines)
                                 for name, marker in patterns.items()},
        )
    catalog = observe('head', '-c', '1048577', '/home/rocketmq/store/config/topics.json')
    context['local_topic_catalog'] = {'available': False}
    if catalog is not None and catalog.returncode == 0 and len(catalog.stdout.encode()) <= 1048576:
        try:
            topics = json.loads(catalog.stdout)['topicConfigTable']
            if isinstance(topics, dict):
                context['local_topic_catalog'] = {'available': True, 'discard_present': TOPIC in topics}
        except (KeyError, TypeError, ValueError):
            pass
    for kind, topic in (('half', 'RMQ_SYS_TRANS_HALF_TOPIC'), ('discard', TOPIC)):
        result = observe('java', '-Xms32m', '-Xmx128m', '-cp', '/opt/rocketmq/conf:/opt/rocketmq/lib/*',
                         'org.apache.rocketmq.tools.command.MQAdminStartup', 'topicStatus',
                         '-n', 'nameserver:9876', '-t', topic)
        if result is None:
            context[kind + '_topic_status'] = {'available': False, 'transport_unavailable': True}
            continue
        raw = result.stdout + result.stderr
        rows = [fields for line in result.stdout.splitlines() if len(fields := line.split()) >= 4
                and all(re.fullmatch(r'[0-9]{1,18}', value) for value in fields[1:4])]
        header = '#Min Offset' in result.stdout and '#Max Offset' in result.stdout
        available = result.returncode == 0 and 'Exception' not in raw and header and len(rows) <= 8
        context[kind + '_topic_status'] = {
            'available': available, 'no_route_reported': 'No topic route' in raw,
            'queues': [dict(queue=int(row[1]), min_offset=int(row[2]), max_offset=int(row[3]))
                       for row in rows] if available else [],
        }
    return context


class OriginalConsumer:
    def __init__(self, native, identity, wire_sha256):
        self.native = native
        self.identity = identity
        self.wire_sha256 = wire_sha256

    def wait(self, event, identity, decision, *, timeout):
        if (event, identity, decision) != ('received', self.identity, self.wire_sha256):
            raise RuntimeError('exact original AI consumer identity required')
        self.native.send('observe')
        if self.native.wait('observed', timeout=timeout) != {
            'event': 'observed', 'wire_sha256': self.wire_sha256, 'broker_ack': True,
        }:
            raise RuntimeError('original AI consumer did not read back the first wire')


def run_managed(managed, directory, broker, project, run, native, proof,
                half, closed, index, evidence_path):
    from managed_recovery_acceptance import accept, install_java_helper

    repo = Path(__file__).resolve().parents[2]
    image = managed['image']
    java = None if image else install_java_helper(repo, directory, broker, project, run, proof)
    identity = half['key']
    original = dict(owner='ai.mysql', store_id=half['store_id'], writer_epoch='m3-1',
                    database=managed['schema'], user='root', operation_id=half['operation_id'],
                    branch_id=half['branch_id'], fence=half['fence'], wire_hash=closed['wire_sha256'],
                    business_count_sql="SELECT COUNT(*) FROM evaluation_runs WHERE run_id='"
                    + half['run_id'] + "' AND JSON_EXTRACT(progress_json,'$.preflight.evaluated_at') IS NOT NULL",
                    writer='actual AI evaluation preflight SQLAlchemy root',
                    scope='one owned original AI commit, approved native recheck and named host reopen')
    def sql(statement):
        return run(['docker', 'exec', '-i', '-e', 'MYSQL_PWD=' + managed['password'],
                    project + '-mysql-1', 'mysql', '-uroot', '--batch', '--skip-column-names',
                    original['database']], stdin=statement).stdout.strip()

    proof['stage'] = 'managed_original_recovery'
    cases = {}
    accept(repo=repo, binary=managed['binary'], broker=broker, project=project, directory=directory,
           manifest=managed['manifest'], route=managed['route'], account=managed['account'],
           grpc_port=managed['grpc_port'], mysql_port=managed['mysql_port'], password=managed['password'],
           ca=managed['ca'], java=java, identity=identity, index_path=evidence_path,
           index=index, sql=sql, run=run, consumer=OriginalConsumer(native, identity, original['wire_hash']),
           passed=lambda name: cases.update({name: True}), proof=proof, original=original, image=image)
    proof['stage'] = 'named_ai_reopen'
    native.send('verify')
    reopened = native.wait('reopened', timeout=60)
    if reopened != {'event': 'reopened', 'original_wire_preserved': True, 'no_new_half': True}:
        raise RuntimeError('named original AI owner reopening proof required')
    proof['ai_reopen'] = dict(named=True, same_wire=True, broker_ack=True, no_new_half=True)
    cases['named_ai_reopen_keeps_first_witness_and_sends_no_new_half'] = True
    return cases


def run_origin(source, directory, broker, project, command, env, run, native_runner,
               read_parameters, proof, evidence_path, *, managed=None):
    if not project.startswith('rocketmq-m2-') or directory.stat().st_mode & 0o077:
        raise RuntimeError('owned private AI origin fixture required')
    admin = Admin(broker)
    before = read_parameters(admin('getBrokerConfig'))
    network = run(['docker', 'inspect', '--format',
                   '{{range $name,$config := .NetworkSettings.Networks}}{{$name}}{{end}}', broker]).stdout.strip()
    if not network.startswith(project + '_') or (
        json.loads(run(['docker', 'network', 'inspect', network]).stdout)[0]['Labels']['com.docker.compose.project'] != project
    ):
        raise RuntimeError('owned Broker network required')
    reconnect = ['docker', 'network', 'connect', '--alias', 'broker']
    if os.environ.get('QS_AI_COORDINATED_IMAGE') == 'true':
        address = run(['docker', 'inspect', '--format',
                       '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', broker]).stdout.strip()
        if address != '172.31.80.10':
            raise RuntimeError('fixed original Broker bridge address required')
        reconnect += ['--ip', address]
    test_file = Path(__file__).with_name('ai_native_origin_case.py').resolve()
    proof['case_sha256'] = hashlib.sha256(test_file.read_bytes()).hexdigest()
    proof['stage'] = 'configuration'

    cases = {}

    def supervise_original(native):
        proof['stage'] = 'original_half'
        half = native.wait('half', timeout=90)
        identity_fields = {'key'}
        if managed:
            identity_fields |= {'operation_id', 'branch_id', 'store_id', 'run_id'}
        expected_fields = identity_fields | ({'fence'} if managed else set()) | {'event'}
        if set(half) != expected_fields or not all(
            isinstance(half[field], str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', half[field])
            for field in identity_fields
        ) or (managed and (type(half['fence']) is not int or not 0 < half['fence'] < 2**63)):
            raise RuntimeError('bounded original message identity required')
        proof['stage'] = 'commit_without_broker'
        run(['docker', 'network', 'disconnect', network, broker])
        try:
            native.send('commit')
            closed = native.wait('closed', timeout=85)
        finally:
            run([*reconnect, network, broker])
        if set(closed) != {'event', 'reference_sha256', 'wire_sha256'} or not all(
            re.fullmatch('[0-9a-f]{64}', closed[field]) for field in ('reference_sha256', 'wire_sha256')
        ):
            raise RuntimeError('original durable witness and wire proof required')
        proof.update(reference_sha256=closed['reference_sha256'], wire_sha256=closed['wire_sha256'],
                     disconnected_root_commit_and_sender_drained=True, stage='original_sys_index')
        started = time.monotonic()
        deadline = started + 110
        index = None
        polls = []
        proof['original_sys_index_polls'] = polls
        while time.monotonic() < deadline:
            try:
                index = export(broker, project, half['key'], evidence_path)
            except RuntimeError as error:
                category = {
                    'native transaction limit index evidence absent': 'absent',
                    'private read-only audit unavailable': 'transport_unavailable',
                    'private read-only audit failed': 'command_failed',
                    'unexpected pinned native limit index format': 'format_rejected',
                    'Compose project mismatch': 'project_mismatch',
                }.get(str(error), 'other_audit_error')
                polls.append(dict(elapsed_ms=int((time.monotonic() - started) * 1000), outcome=category))
                time.sleep(2)
            else:
                polls.append(dict(elapsed_ms=int((time.monotonic() - started) * 1000),
                                  outcome='exported', records=len(index['records']),
                                  truncated_possible=index['truncated_possible']))
                break
        if not index or len(index['records']) != 1 or index['truncated_possible'] or not (
            index['read_only'] and not index['body_exported']
        ):
            try:
                proof['original_sys_index_context'] = sys_index_context(run, broker, half['key'])
            except (OSError, ValueError, RuntimeError):
                proof['original_sys_index_context'] = {'available': False}
            raise RuntimeError('one original native SYS index required')
        digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        proof.update(native_index_sha256=digest, native_index_records=1, stage='original_notice')
        native.send('record')
        if native.wait('blocked', timeout=35) != {'event': 'blocked', 'evidence_sha256': digest}:
            raise RuntimeError('exact original native notice required')
        if managed:
            admin('updateBrokerConfig', '-k', 'transactionCheckMax', '-v', str(before['transactionCheckMax']))
            if read_parameters(admin('getBrokerConfig')) != before:
                raise RuntimeError('original Broker budget required before recovery')
            cases.update(run_managed(managed, directory, broker, project, run, native,
                                     proof, half, closed, index, evidence_path))

    def supervise(native):
        try:
            supervise_original(native)
        except Exception:
            native.drain()
            allowed = {'recovery_observer_started', 'replacement_started', 'replacement_blocked', 'first_wire_seen', 'observed'}
            proof['ai_consumer_checkpoints'] = [
                event['event'] for event in native.events if event.get('event') in allowed
            ]
            native.log.flush()
            raw = Path(native.log.name).read_text(errors='replace')
            proof['ai_case_assertion_lines'] = sorted({
                int(line) for line in re.findall(r'ai_native_origin_case[.]py:(\d+):', raw)
            })
            proof['ai_exception_types'] = sorted(set(re.findall(
                r'^E[ \t]+(AssertionError|AttributeError|RuntimeError|TimeoutError|ValueError|ValidationError)\b',
                raw, re.MULTILINE,
            )))
            raise

    try:
        admin('updateBrokerConfig', '-k', 'transactionCheckMax', '-v', '2')
        effective = read_parameters(admin('getBrokerConfig'))
        if effective != dict(before, transactionCheckMax=2):
            raise RuntimeError('isolated Broker check budget required')
        junit = directory / 'ai-native-origin-private.xml'
        result = native_runner([*command, 'python', '-m', 'pytest', '-q', '-s',
                                 '-c', str(source / 'pyproject.toml'), str(test_file), '--junitxml=' + str(junit)],
                                cwd=source, env=env, timeout=800 if managed else 355,
                                prefix='AI_NATIVE_ORIGIN ', supervise=supervise)
        if result.returncode or not junit.is_file():
            raise RuntimeError('isolated original AI host acceptance failed')
        test_cases = ElementTree.parse(junit).findall('.//testcase')
        if (len(test_cases) != 1 or test_cases[0].get('name') != 'test_original_ai_root_reaches_native_limit'
                or any(test_cases[0].find(tag) is not None for tag in ('failure', 'error', 'skipped'))):
            raise RuntimeError('one actual AI original case must pass without skip')
    finally:
        admin('updateBrokerConfig', '-k', 'transactionCheckMax', '-v', str(before['transactionCheckMax']))
        proof['broker_parameters_restored'] = read_parameters(admin('getBrokerConfig')) == before
    if not proof['broker_parameters_restored']:
        raise RuntimeError('isolated Broker parameters were not restored')
    proof['stage'] = 'verified'
    return {'cases': {'actual_ai_original_root': True, 'same_root_sys_limit': True,
                      'original_notice_keeps_witness': True, **cases}}
