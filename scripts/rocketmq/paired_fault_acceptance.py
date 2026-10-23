"""Strict paired original-root fault gates, with an owned real Broker process."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import xml.etree.ElementTree as ET

from paired_acceptance import FULL_CASES, FULL_TESTS, paired_manifest, read_receipt

SDK_SHA256 = '7a0a35438ed6890cff37aea3305e1ee1fcec4b9bcac0667959fbc2cda62c636e'

SCOPE = 'actual paired Go QS/Python AI original roots with MQ disconnect, producer SIGKILL and Broker SIGKILL/restart'
CASES = frozenset((
    'half_ack_before_actual_mq_disconnect', 'old_local_committed_final_unknown',
    'producer_sigkill_exit_negative9', 'same_primary_epoch_readonly_resume_no_new_half',
    'new_paused_broker_commit_callback', 'same_first_command_wire_after_resume',
    'recovered_pair_receipt_state_ack_without_model', 'recovered_process_resources_drained',
    'ai_half_prepared_before_broker_kill', 'actual_final_rpc_unknown_after_committed_root',
    'broker_sigkill_and_same_container_restart', 'broker_recheck_original_ai_first_wire',
    'pair_both_business_acks_without_executor_replay', 'no_additional_model_or_old_business_executor',
    'broker_fault_resources_drained'))
TESTS = frozenset('test_actual_paired_fault_recovery[' + mode + ']'
                  for mode in ('qs_sigkill', 'broker_restart'))
FIELDS = {'source_sha','qs_source_sha','profile','passed','failed','skipped','cases','proof',
          'scope','public_http_real_provider_system_production_not_claimed','synthetic_read_side'}


def profile():
    if os.environ.get('QS_M3_PAIRED_PROFILE', 'core') not in ('core', 'full'):
        raise ValueError('explicit paired fault core/full profile required')
    return dict(name='paired_faults',sdk_version='0.4.0a3',
        sdk_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.4.0a3/fangcun_reliable_messaging-0.4.0a3-py3-none-any.whl',
        sdk_sha256=SDK_SHA256,manifest=paired_manifest,file='rocketmq_paired_faults.py',scope=SCOPE)


def bounded_int(value, minimum=0, maximum=1024):
    return type(value) is int and minimum <= value <= maximum


def parse_receipt(output, junit, ai_sha, qs_sha, *, full, sdk_python="0.4.0a2"):
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
    b_expected = dict(local_calls=1,checks_drained_before_restart=True,half_prepared_before_kill=2,local_calls_before_kill=0,half_prepared=2,actual_final_unknown=2,pending_calls=0,
        provider_invocations=0,original_host_failed_and_drained=True,new_host_runtime=True,
        recovered_half_prepared=0,recovered_completed_results=0,recovered_committed_references=2)
    for row, expected, count, original, replacements in (
            (q,q_expected,'recovered_broker_commit_checks',-9,[0]),
            (b,b_expected,'broker_commit_checks',0,[])):
        if (not isinstance(row,dict) or set(row) != set(expected) | {count,'resources'}
                or any(type(row[k]) is not type(v) or row[k] != v for k,v in expected.items())
                or not bounded_int(row[count],1)
                or not isinstance(row['resources'],dict)
                or type(row['resources'].get('original_exit_code')) is not int
                or not isinstance(row['resources'].get('replacement_exit_codes'),list)
                or any(type(code) is not int for code in row['resources']['replacement_exit_codes'])
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
        baseline = read_receipt(output,full=True,marker='M3_PAIRED_BASELINE_RECEIPT ',sdk_python=sdk_python)
        if baseline is None:
            raise RuntimeError('mandatory baseline paired regression incomplete')
        combined.update(baseline['cases'])
        r['baseline'] = baseline
    r['combined_cases'] = combined
    return r



def read_partial_receipt(output, ai_sha, qs_sha):
    """Export only fixed case names and integer diagnostics from failed native output."""
    marker = 'M3_PAIRED_FAULT_RECEIPT '
    lines = [line.split(marker,1)[1] for line in output.splitlines() if marker+'{' in line]
    if len(lines) != 1 or len(lines[0]) > 16384:
        return None
    try:
        r = json.loads(lines[0])
    except (ValueError,TypeError):
        return None
    if (not isinstance(r,dict) or r.get('source_sha') != ai_sha or r.get('qs_source_sha') != qs_sha
            or r.get('scope') != SCOPE or not isinstance(r.get('cases'),dict)
            or not set(r['cases']).issubset(CASES) or any(v is not True for v in r['cases'].values())
            or any(not bounded_int(r.get(k),0) for k in ('passed','failed','skipped'))
            or r['passed'] != len(r['cases']) or not isinstance(r.get('proof'),dict)):
        return None
    allowed = ('half_prepared_before_loss','old_exit_code','old_seals',
        'recovered_completed_results','recovered_half_prepared','recovered_broker_commit_checks',
        'final_recovered_seals','provider_invocations','local_calls','half_prepared',
        'actual_final_unknown','broker_commit_checks','pending_calls',
        'half_prepared_before_kill','local_calls_before_kill','recovered_committed_references')
    counters = {}
    for fault in ('qs_sigkill','broker_restart'):
        row = r['proof'].get(fault)
        if isinstance(row,dict):
            counters[fault] = {key:row[key] for key in allowed if bounded_int(row.get(key),-9)}
    return dict(cases=r['cases'],passed=r['passed'],failed=r['failed'],skipped=r['skipped'],
        counters=counters,partial=True,complete_acceptance_claimed=False)


def write_control(path, content):
    if path.exists() or path.parent.stat().st_mode & 0o077:
        raise RuntimeError('new control in owned0700 fixture required')
    fd = os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as stream:
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
            native.wait('ai_half_prepared',timeout=600)
            proof['broker_kill'] = broker_fault.kill()
            write_control(paths['broker_killed'],'broker-killed')
            native.wait('final_unknown_observed',timeout=80)
            proof['broker_restart'] = broker_fault.start()
            proof['topic_routes_ready'] = broker_fault.wait_topic_routes(
                sorted({r['physical_topic'] for r in config['routes']}))
            from route_read_probe import parse_output
            proof['proxy_routes_ready'] = []
            for ordinal, topic in enumerate(sorted({r['physical_topic'] for r in config['routes']})):
                private = directory / ('paired-proxy-route-' + str(ordinal) + '.json')
                write_control(private,json.dumps(dict(endpoint=config['endpoint'],ca=config['ca_file'],
                    topic=topic,accesskey=config['ai']['username'],secretkey=config['ai']['password'])))
                response = run([*command,'python',str(Path(__file__).with_name('route_read_probe.py')),
                    '--config',str(private),'--mode','route-read'],cwd=source,env=env,timeout=65)
                proof['proxy_routes_ready'].append(parse_output(response.stdout,topic))
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
        from ai_admission_acceptance import host_failure_diagnostics
        proof['diagnostics'] = host_failure_diagnostics(raw,
            ('rocketmq_paired_host.py','rocketmq_paired_faults.py'),
            TESTS | (FULL_TESTS if full else frozenset()))
        partial = read_receipt(raw,full=full,partial=True,marker='M3_PAIRED_BASELINE_RECEIPT ',
            sdk_python=config['sdk_python_version'])
        if partial is not None:
            proof['partial_baseline_receipt'] = partial
        fault_partial = read_partial_receipt(raw,proof['source_sha'],proof['paired_qs']['source_sha'])
        if fault_partial is not None:
            proof['partial_fault_receipt'] = fault_partial
        raise RuntimeError('actual paired host fault failed; private output withheld')
    proof['junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
    receipt = parse_receipt(raw,junit.read_text(),proof['source_sha'],proof['paired_qs']['source_sha'],full=full,sdk_python=config['sdk_python_version'])
    proof['native_receipt'] = receipt
    proof['native_tests_passed'] = 7 if full else 2
    for current, expected in ((source,proof['source_sha']),
            (Path(os.environ['QS_M3_PAIRED_SOURCE']),proof['paired_qs']['source_sha'])):
        if (run(['git','status','--porcelain'],cwd=current).stdout.strip()
                or run(['git','rev-parse','HEAD'],cwd=current).stdout.strip() != expected):
            raise RuntimeError('paired host source changed during fault acceptance')
    proof['source_clean_after'] = proof['paired_qs']['source_clean_after'] = True
    proof['scope'] = SCOPE
