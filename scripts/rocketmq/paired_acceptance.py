"""Final-version paired host gates. Core is development-only; full is mandatory."""
import hashlib
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from routes import consumer_group_v2, physical_topic_v2, validate_v2

CORE_TEST = 'test_actual_qs_ai_original_start_receipt_state_and_ack_loop'
CORE_CASES = frozenset((
    'actual_ai_default_receivers_and_idle_checker', 'actual_go_command_and_event_runtime',
    'no_legacy_relay', 'owned_processes_rpc_and_private_files_closed',
    'actual_qs_service_and_command_root', 'actual_qs_receipt_state_and_first_ack_roots',
    'actual_ai_admission_archive_and_witness', 'first_command_and_ack_wire_cross_language',
    'actual_ai_business_receipts_and_history', 'no_new_publish_outbox_or_model_call'))
FULL_TESTS = frozenset((CORE_TEST,
    'test_actual_qs_ai_first_wire_and_duplicate_command_event_ack',
    'test_actual_qs_ai_large_payloads_and_mtls_denial',
    'test_actual_qs_ai_original_cancellation_preserves_final_state',
    'test_actual_qs_ai_evaluation_start_cancel_receipt_state_ack'))
FULL_CASES = CORE_CASES | frozenset((
    'duplicate_original_command_no_new_seal', 'duplicate_event_uses_first_ack',
    'duplicate_ack_keeps_first_receipt', 'cross_language_first_wire_unchanged',
    'duplicate_delivery_does_not_authorize_business_retry', 'actual_go_large_command_body_rpc',
    'actual_ai_large_state_body_rpc', 'wrong_peer_mtls_denied_both_hosts',
    'wrong_reference_never_serves_body_both_hosts', 'interpretation_cancel_original_roots',
    'cancel_duplicate_no_new_event', 'cancel_no_provider_or_attempt_change',
    'evaluation_start_original_roots', 'evaluation_cancel_original_roots',
    'evaluation_receipt_state_ack_sequence'))
FLAGS = frozenset(('system_login_not_claimed', 'real_provider_not_claimed',
    'public_http_not_claimed', 'packet_fault_not_claimed', 'synthetic_evidence_source'))
FIELDS = FLAGS | {'cases','passed','failed','skipped','root','sdk_go','sdk_python',
                 'client_python','python','profile','go_phase','delivery_errors','last_observation'}
GO_PHASES = frozenset(('not_started','ready','invalid_ready','private_configuration',
    'mysql_admin','create_owned_schema','mysql_primary','mysql_pool','migration_source',
    'explicit_migrations','owner_binding','fixture_admission','local_workload_keys',
    'shared_owner','original_commands','original_events','payload_ca','payload_certificate',
    'payload_client','event_runtime','owner_start','owner_admission','consumer_start',
    'payload_listener','control_ready','drop_owned_schema','owner_close','consumer_close',
    'payload_close','control_write','control_read','control_received','control_output',
    'control_waiting','facts_operation','facts_evaluation_projection','facts_projection',
    'facts_command_archive','facts_archive_identities','facts_archive_evidence','facts_counts'))
DELIVERY_ERRORS = frozenset({'other'} | {'grpc_' + name for name in (
    'OK','CANCELLED','UNKNOWN','INVALID_ARGUMENT','DEADLINE_EXCEEDED','NOT_FOUND',
    'ALREADY_EXISTS','PERMISSION_DENIED','RESOURCE_EXHAUSTED','FAILED_PRECONDITION',
    'ABORTED','OUT_OF_RANGE','UNIMPLEMENTED','INTERNAL','UNAVAILABLE','DATA_LOSS',
    'UNAUTHENTICATED')})


def valid_observation(value):
    return (isinstance(value,dict)
        and set(value) == {'polls','payload_calls','ack_count','operation_status',
                          'projection_version','projection_status','ai_payload_reads'}
        and all(type(value[k]) is int and 0 <= value[k] <= 100000
                for k in ('polls','payload_calls','ack_count','projection_version','ai_payload_reads'))
        and isinstance(value['projection_status'],str)
        and value['projection_status'] in {'missing','queued','running','awaiting_answer',
                                           'blocked','cancelled','completed'}
        and isinstance(value['operation_status'],str)
        and value['operation_status'] in {'unobserved','submitted','accepted','held','rejected'})


MARKER = 'M3_PAIRED_HOST_RECEIPT '
SDK_SHA256 = '570822f9ed51eee25001624858d30b7433468eb7da59e34348289c50a37cabb2'


def paired_manifest():
    routes = []
    for name, topic, subscription, owner in (
        ('command','qs.ai.commands.v1','qs-ai.commands.v1','qs.mysql'),
        ('event','qs.ai.events.v1','qs-server.ai-events.v1','ai.mysql'),
        ('ack','qs.ai.acks.v1','qs-ai.acks.v1','qs.mysql')):
        routes.append(dict(id='paired-'+name,topic=topic,subscription=subscription,
            message_type='TRANSACTION',owner=owner,route_revision='m3-1',
            physical_topic=physical_topic_v2(topic,'TRANSACTION',owner,'m3-1'),
            consumer_group=consumer_group_v2(topic,subscription)))
    command,event,ack = (r['id'] for r in routes)
    manifest = dict(version=2,routes=routes,
        topic_options=dict(read_queue_nums=1,write_queue_nums=1,perm=6),
        group_options=dict(retry_queue_nums=8),accounts={
            'qs':dict(owner='qs.mysql',publish=[command,ack],subscriptions=[event]),
            'ai':dict(owner='ai.mysql',publish=[event],subscriptions=[command,ack])})
    validate_v2(manifest)
    return manifest


def read_receipt(output, *, full=False, partial=False, marker=MARKER):
    lines = [line.split(marker,1)[1] for line in output.splitlines() if marker+'{' in line]
    if len(lines) != 1 or len(lines[0]) > 16384:
        return None
    try:
        value = json.loads(lines[0])
    except (ValueError, TypeError):
        return None
    expected = FULL_CASES if full else CORE_CASES
    if (not isinstance(value,dict) or set(value) != FIELDS
            or any(value[k] is not True for k in FLAGS)
            or value['root'] != 'original_go_mysql_and_python_sqlalchemy'
            or (value['sdk_go'],value['sdk_python'],value['client_python']) != (
                'v0.5.0-rocketmq-tx.2','0.4.0a2','5.1.2')
            or value['profile'] != ('full' if full else 'core')
            or not isinstance(value['delivery_errors'],list)
            or any(not isinstance(v,str) or v not in DELIVERY_ERRORS for v in value['delivery_errors'])
            or len(value['delivery_errors']) > len(DELIVERY_ERRORS)
            or not valid_observation(value['last_observation'])
            or not isinstance(value['go_phase'],str) or value['go_phase'] not in GO_PHASES
            or not isinstance(value['python'],str)
            or re.fullmatch(r'3\.(11|13)\.\d{1,3}',value['python']) is None
            or any(type(value[k]) is not int for k in ('passed','failed','skipped'))
            or any(not 0 <= value[k] <= 1000 for k in ('passed','failed','skipped'))
            or not isinstance(value['cases'],dict) or not set(value['cases']).issubset(expected)
            or any(v is not True for v in value['cases'].values())
            or value['passed'] != len(value['cases'])):
        return None
    if not partial and (value['go_phase'] != 'ready'
                        or (value['passed'],value['failed'],value['skipped']) != (len(expected),0,0)
                        or set(value['cases']) != expected):
        return None
    return value


def parse_receipt(output, junit, *, full=False):
    value = read_receipt(output,full=full)
    tests = FULL_TESTS if full else {CORE_TEST}
    cases = list(ET.fromstring(junit).iter('testcase'))
    if (value is None or len(cases) != len(tests) or {c.get('name') for c in cases} != tests
            or any(c.get('classname') != 'tests.integration.rocketmq_paired_host' for c in cases)
            or any(c.find(tag) is not None for c in cases for tag in ('error','failure','skipped'))):
        raise RuntimeError('required paired host profile incomplete, failed, skipped or substituted')
    return value


def profile():
    kind = os.environ.get('QS_M3_PAIRED_PROFILE','core')
    if kind not in ('core','full'):
        raise ValueError('explicit paired core/full profile required')
    full = kind == 'full'
    from ai_finalization_characterization import diagnostics
    return dict(name='paired',sdk_version='0.4.0a2',
        sdk_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.4.0a2/fangcun_reliable_messaging-0.4.0a2-py3-none-any.whl',
        sdk_sha256=SDK_SHA256,file='rocketmq_paired_host.py',manifest=paired_manifest,
        partial=lambda output:read_receipt(output,full=full,partial=True),
        parse=lambda output,junit:parse_receipt(output,junit,full=full),
        tests=FULL_TESTS if full else {CORE_TEST},
        failure_diagnostics=lambda raw:diagnostics(raw,tests=FULL_TESTS if full else {CORE_TEST}),
        fail_fast=True,pytest_selection=[] if full else ['-k',CORE_TEST],
        scope=('full mandatory final-version paired gate; duplicate delivery is controlled at original receivers, physical transport faults are T23' if full else 'core development gate; does not satisfy T20-C/D')
            + '; actual Go QS/Python AI default consumers and original roots; synthetic read-side source, no real provider/public HTTP/system or packet-fault claim')


def prepare_qs(source,directory,project,mysql_port,password,run,proof):
    source = source.resolve()
    if (not (source/'go.mod').is_file()
            or run(['git','status','--porcelain'],cwd=source).stdout.strip()):
        raise ValueError('exact clean paired QS host checkout required')
    sha = run(['git','rev-parse','HEAD'],cwd=source).stdout.strip()
    if re.fullmatch('[0-9a-f]{40}',sha) is None:
        raise ValueError('exact paired QS source required')
    env = dict(os.environ,GOWORK='off',GOFLAGS='-mod=readonly')
    module = json.loads(run(['go','list','-m','-json','github.com/FangcunMount/reliable-messaging'],cwd=source,env=env).stdout)
    if (module.get('Replace') or module.get('Version') != 'v0.5.0-rocketmq-tx.2' or module.get('Sum') != 'h1:kBHB/1aG/fAB6BPlITOwRYIX9XazRisz0PgfwyJ1VFY='
            or module.get('GoModSum') != 'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I='):
        raise ValueError('fixed published QS host SDK required')
    go_version = run(['go','version'],cwd=source,env=env).stdout.strip()
    if re.match(r'go version go1\.25\.12(?: |$)',go_version) is None:
        raise ValueError('actual QS host Go 1.25.12 runtime required')
    binary = directory/'qs-paired-host'
    run(['go','build','-p','1','-race','-tags=m3_ai_paired','-o',str(binary),
         './tests/m3_ai_paired_probe'],cwd=source,env=env,timeout=300)
    binary.chmod(0o700)
    module = {k:module[k] for k in ('Path','Version','Sum','GoModSum')}
    proof['paired_qs'] = dict(source_sha=sha,sdk_module=module,go_version=go_version,
        helper_source_sha256=hashlib.sha256((source/'tests/m3_ai_paired_probe/main.go').read_bytes()).hexdigest(),
        helper_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    return dict(qs_source=str(source),qs_source_sha=sha,qs_binary=str(binary),
        qs_sdk_module=module,qs_dsn=f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
        project=project,private_directory=str(directory),
        paired_profile=os.environ.get('QS_M3_PAIRED_PROFILE','core'))
