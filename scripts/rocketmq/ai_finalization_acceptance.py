"""Strict separate-process HTTP/worker/Broker proof, independent from T17 state profile."""
import json
import re
import xml.etree.ElementTree as ET
from ai_finalization_characterization import diagnostics

from routes import consumer_group_v2, physical_topic_v2, validate_v2

CASES = frozenset(('external_http_counter', 'no_new_publish_outbox',
    'sigkill_after_committed_response', 'replacement_reuses_original_response',
    'normal_broker_delivery', 'recovery_broker_delivery', 'normal_actual_worker',
    'recovery_actual_worker', 'normal_witness_and_archive', 'recovery_witness_and_archive',
    'rpc_proxy_forwarding', 'all_owned_processes_stopped'))
PATHS = ('interpretation_report', 'serial_generation', 'serial_semantic',
         'candidate_generation', 'candidate_semantic')
SCENARIOS = ('normal', 'response_committed_terminal_mq_unavailable',
             'terminal_committed_confirmation_lost', 'response_committed_process_sigkill')
MATRIX = frozenset('matrix_' + path + '_' + scenario for path in PATHS for scenario in SCENARIOS)
CASES = CASES | MATRIX
TESTS = (frozenset('test_actual_independent_report_worker_http_counter_and_broker[' + k + ']'
                  for k in ('False', 'True'))
         | frozenset('test_independent_five_path_finalization_matrix[' + scenario + '-' + path + ']'
                     for path in PATHS for scenario in SCENARIOS))
_MARKER = 'M3_AI_FINALIZATION_RECEIPT '
_FLAGS = frozenset(('system_login_not_claimed', 'paired_qs_business_not_claimed',
    'real_external_provider_not_claimed', 'database_commit_network_fault_not_claimed',
    'real_packet_fault_verified', 'five_path_matrix_verified',
    'real_http_counter_verified', 'process_sigkill_verified'))
_FIELDS = _FLAGS | {'cases', 'passed', 'failed', 'skipped', 'root', 'sdk', 'client', 'python'}


def finalization_manifest():
    topic, subscription = 'qs.ai.events.v1', 'qs-m3-ai-state-observer'
    route = dict(id='ai-finalization-event', topic=topic, subscription=subscription,
        message_type='TRANSACTION', owner='ai.mysql', route_revision='m3-1',
        physical_topic=physical_topic_v2(topic, 'TRANSACTION', 'ai.mysql', 'm3-1'),
        consumer_group=consumer_group_v2(topic, subscription))
    manifest = dict(version=2, routes=[route],
        topic_options=dict(read_queue_nums=1, write_queue_nums=1, perm=6),
        group_options=dict(retry_queue_nums=8),
        accounts=dict(ai=dict(owner='ai.mysql', publish=[route['id']], subscriptions=[]),
                      observer=dict(publish=[], subscriptions=[route['id']])))
    validate_v2(manifest)
    return manifest


def read_receipt(output, *, sdk_version='0.4.0a2'):
    lines = [line.split(_MARKER, 1)[1] for line in output.splitlines() if _MARKER + '{' in line]
    if len(lines) != 1:
        return None
    try:
        value = json.loads(lines[0])
    except (ValueError, TypeError):
        return None
    if (not isinstance(value, dict) or set(value) != _FIELDS
            or not isinstance(value['cases'], dict) or not set(value['cases']) <= CASES
            or any(v is not True for v in value['cases'].values())
            or any(type(value[k]) is not int or not 0 <= value[k] <= 100 for k in ('passed', 'failed', 'skipped'))
            or value['passed'] != len(value['cases']) or value['root'] != 'original_mysql_sqlalchemy'
            or value['sdk'] != sdk_version or value['client'] != '5.1.2'
            or re.fullmatch(r'3\.(?:11|13)\.\d{1,3}', value['python']) is None
            or any(type(value[k]) is not bool for k in _FLAGS)):
        return None
    return value


def parse_receipt(output, junit, *, sdk_version='0.4.0a2'):
    value = read_receipt(output, sdk_version=sdk_version)
    if (value is None or set(value['cases']) != CASES
            or value['failed'] != 0 or value['skipped'] != 0
            or any(value[k] is not True for k in _FLAGS)):
        raise RuntimeError('independent finalization receipt absent or incomplete')
    cases = list(ET.fromstring(junit).iter('testcase'))
    if (len(cases) != len(TESTS) or {c.get('name') for c in cases} != TESTS
            or any(c.find(k) is not None for c in cases for k in ('failure', 'error', 'skipped'))):
        raise RuntimeError('independent finalization native tests failed, skipped or absent')
    return value


def profile():
    return dict(name='finalization', sdk_version='0.4.0a2',
        sdk_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.4.0a2/fangcun_reliable_messaging-0.4.0a2-py3-none-any.whl',
        sdk_sha256='570822f9ed51eee25001624858d30b7433468eb7da59e34348289c50a37cabb2',
        file='rocketmq_finalization_host.py', manifest=finalization_manifest, fail_fast=True,
        diagnostic_files=('rocketmq_finalization_host.py', 'rocketmq_finalization_matrix.py'),
        failure_diagnostics=lambda raw: diagnostics(raw, tests=TESTS),
        partial=read_receipt, parse=parse_receipt, tests=TESTS,
        scope='five original report/serial/candidate worker paths in independent processes; synthetic HTTP provider with external persistent counter; real MySQL/SDK/Broker; actual terminal SendMessage and EndTransaction TCP reply loss; response-committed SIGKILL/recovery; observer ACK only, no paired QS/system or database commit network-fault proof')
