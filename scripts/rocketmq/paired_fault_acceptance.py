"""Strict paired original-root fault gates, with an owned real Broker process."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import xml.etree.ElementTree as ET

from paired_acceptance import FULL_CASES, FULL_TESTS, paired_manifest, read_receipt, SDK_SHA256

SCOPE = 'actual paired Go QS/Python AI original roots with MQ disconnect, producer SIGKILL and Broker SIGKILL/restart'
CASES = frozenset((
    'half_ack_before_actual_mq_disconnect', 'old_local_committed_final_unknown',
    'producer_sigkill_exit_negative9', 'same_primary_epoch_readonly_resume_no_new_half',
    'new_paused_broker_commit_callback', 'same_first_command_wire_after_resume',
    'recovered_pair_receipt_state_ack_without_model', 'recovered_process_resources_drained',
    'ai_root_witness_committed_before_broker_kill', 'actual_final_rpc_unknown_after_committed_root',
    'broker_sigkill_and_same_container_restart', 'broker_recheck_original_ai_first_wire',
    'pair_both_business_acks_and_idempotent_redelivery', 'no_additional_model_or_old_business_executor',
    'broker_fault_resources_drained'))
TESTS = frozenset('test_actual_paired_fault_recovery[' + mode + ']'
                  for mode in ('qs_sigkill', 'broker_restart'))
FIELDS = {'source_sha','qs_source_sha','profile','passed','failed','skipped','cases','proof',
          'scope','public_http_real_provider_system_production_not_claimed','synthetic_read_side'}


def profile():
    if os.environ.get('QS_M3_PAIRED_PROFILE', 'core') not in ('core', 'full'):
        raise ValueError('explicit paired fault core/full profile required')
    return dict(name='paired_faults',sdk_version='0.4.0a2',
        sdk_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.4.0a2/fangcun_reliable_messaging-0.4.0a2-py3-none-any.whl',
        sdk_sha256=SDK_SHA256,manifest=paired_manifest,file='rocketmq_paired_faults.py',scope=SCOPE)


def bounded_int(value, minimum=0, maximum=1024):
    return type(value) is int and minimum <= value <= maximum


def parse_receipt(output, junit, ai_sha, qs_sha, *, full):
    marker = 'M3_PAIRED_FAULT_RECEIPT '
    lines = [line.split(marker, 1)[1] for line in output.splitlines() if marker + '{' in line]
    if len(lines) != 1 or len(lines[0]) > 16384:
        raise RuntimeError('one bounded paired fault receipt required')
    r = json.loads(lines[0])
    if (not isinstance(r, dict) or set(r) != FIELDS
            or not all(re.fullmatch('[0-9a-f]{40}', sha) for sha in (ai_sha,qs_sha))
            or r['source_sha'] != ai_sha or r['qs_source_sha'] != qs_sha
            or r['profile'] != ('full' if full else 'core') or r['scope'] != SCOPE
            or r['public_http_real_provider_system_production_not_claimed'] is not True
            or r['synthetic_read_side'] is not True or not isinstance(r['cases'],dict)
            or set(r['cases']) != CASES or any(v is not True for v in r['cases'].values())
            or any(type(r[k]) is not int for k in ('passed','failed','skipped'))
            or (r['passed'],r['failed'],r['skipped']) != (15,0,0)):
        raise RuntimeError('paired fault source, cases or scope incomplete')
    p = r['proof']
    if not isinstance(p,dict) or set(p) != {'qs_sigkill','broker_restart'}:
        raise RuntimeError('both actual paired faults required')
    q, b = p['qs_sigkill'], p['broker_restart']
    q_expected = dict(half_prepared_before_loss=1,proxy_stopped_before_root_release=True,
        original_root_lock_wait_observed=True,old_exit_code=-9,distinct_producer_pid=True,
        old_seals=1,recovered_completed_results=0,recovered_half_prepared=0,
        original_wire_unchanged=True,final_recovered_seals=2,provider_invocations=0)
    b_expected = dict(local_calls=1,half_prepared=2,actual_final_unknown=2,pending_calls=0,
        provider_invocations=0)
    for row, expected, count, original, replacements in (
            (q,q_expected,'recovered_broker_commit_checks',-9,[0]),
            (b,b_expected,'broker_commit_checks',0,[])):
        if (not isinstance(row,dict) or set(row) != set(expected) | {count,'resources'}
                or any(type(row[k]) is not type(v) or row[k] != v for k,v in expected.items())
                or not bounded_int(row[count],1)
                or row['resources'] != dict(closed=True,private_files_removed=True,
                    original_exit_code=original,replacement_exit_codes=replacements)):
            raise RuntimeError('actual paired fault counters or process/resource proof invalid')
    native = list(ET.fromstring(junit).iter('testcase'))
    expected_tests = TESTS | (FULL_TESTS if full else frozenset())
    if (len(native) != len(expected_tests) or {c.get('name') for c in native} != expected_tests
            or any(c.get('classname') != ('tests.integration.rocketmq_paired_faults'
                if c.get('name') in TESTS else 'tests.integration.rocketmq_paired_host') for c in native)
            or any(c.find(tag) is not None for c in native for tag in ('error','failure','skipped'))):
        raise RuntimeError('native paired fault tests empty, substituted, failed or skipped')
    combined = dict(r['cases'])
    if full:
        baseline = read_receipt(output,full=True,marker='M3_PAIRED_BASELINE_RECEIPT ')
        if baseline is None:
            raise RuntimeError('mandatory baseline paired regression incomplete')
        combined.update(baseline['cases'])
        r['baseline'] = baseline
    r['combined_cases'] = combined
    return r


def write_control(path, content):
    if path.exists() or path.parent.stat().st_mode & 0o077:
        raise RuntimeError('new control in owned0700 fixture required')
    with path.open('x') as stream:
        path.chmod(0o600)
        stream.write(content)


def run_profile(source,directory,env,command,run,proof,native_runner,broker_fault):
    if native_runner is None or broker_fault is None:
        raise RuntimeError('owned native supervision and Broker identity required')
    full = os.environ.get('QS_M3_PAIRED_PROFILE','core') == 'full'
    config_path = Path(env['QS_AI_M3_BROKER_CONFIG'])
    config = json.loads(config_path.read_text())
    paths = {key: directory / ('paired-' + key + '.control') for key in ('broker_killed','broker_ready')}
    config.update(paired_faults=True,fault_control={key:str(path) for key,path in paths.items()})
    config_path.write_text(json.dumps(config)); config_path.chmod(0o600)
    def supervise(native):
        try:
            native.wait('ai_root_committed',timeout=600)
            proof['broker_kill'] = broker_fault.kill()
            write_control(paths['broker_killed'],'broker-killed')
            native.wait('final_unknown_observed',timeout=80)
            proof['broker_restart'] = broker_fault.start()
            write_control(paths['broker_ready'],'broker-ready')
        except Exception:
            proof['supervision_failed'] = True
            native.signal_group(signal.SIGKILL)
    files = ['rocketmq_paired_host.py','rocketmq_paired_faults.py'] if full else ['rocketmq_paired_faults.py']
    junit = directory / 'paired-fault-private.xml'
    result = native_runner([*command,'pytest','-q','-s','-x',
        *(str(source/'tests/integration'/f) for f in files),'--junitxml='+str(junit)],
        cwd=source,env=env,timeout=900,required=False,prefix='M3_PAIRED_FAULT_STATE ',supervise=supervise)
    raw = result.stdout + result.stderr
    private = directory / 'paired-fault-private.log'; private.write_text(raw); private.chmod(0o600)
    proof.update(native_exit_code=result.returncode,private_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        assertion_lines=sorted(set(map(int,re.findall(r'rocketmq_paired_faults\.py:(\d+)',raw))))[:32])
    if junit.exists(): junit.chmod(0o600)
    if result.returncode or not junit.is_file():
        raise RuntimeError('actual paired host fault failed; private output withheld')
    proof['junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
    receipt = parse_receipt(raw,junit.read_text(),proof['source_sha'],proof['paired_qs']['source_sha'],full=full)
    proof['native_receipt'] = receipt
    proof['native_tests_passed'] = 7 if full else 2
    for current in (source,Path(os.environ['QS_M3_PAIRED_SOURCE'])):
        if run(['git','status','--porcelain'],cwd=current).stdout.strip():
            raise RuntimeError('paired host source changed during fault acceptance')
    proof['source_clean_after'] = proof['paired_qs']['source_clean_after'] = True
    proof['scope'] = SCOPE
