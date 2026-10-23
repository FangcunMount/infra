#!/usr/bin/env python3
"""GitHub-only target Compose test, not IAM/QS/AI image or DB acceptance."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch

from audit_transaction_limit import write_private
import cutover_step
import runtime_start as target
from start_boundary import Boundary, BoundaryError, _encoded, initialize


def docker(*args):
    result = subprocess.run([target.DOCKER, '--host', target.SOCKET, *args], capture_output=True, timeout=150)
    if result.returncode != 0:
        raise BoundaryError('owned Docker fixture command failed')
    return result.stdout


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('This real dependency fixture only runs in isolated GitHub Actions')
    run, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
    if not re.fullmatch('[0-9]{1,20}', run) or not re.fullmatch('[0-9]{1,4}', attempt):
        raise SystemExit('Exact owned workflow identity required')
    project = 'm3-runtime-start-' + run + '-' + attempt
    existing = set(docker('ps', '-aq').decode().split())
    existing_networks = set(docker('network', 'ls', '-q').decode().split())
    if docker('ps', '-aq', '--filter', 'label=com.docker.compose.project='+project).strip():
        raise SystemExit('Owned fixture identity already exists; refusing takeover')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    before = subprocess.check_output(['git', 'status', '--porcelain'], text=True)
    report = {'schema': 'm3-target-runtime-start/v1', 'source_sha': source,
              'passed': 0, 'failed': 0, 'skipped': 0, 'cases': {},
              'scope': 'isolated_nsqd_container_as_compose_fixture_not_m3_business_images_or_transactions',
              'production_executed': False, 'cutover_authorized': False,
              'source_clean_before': before == ''}
    plan = None; down_ok = False; owned_root = None; stage = 'fixture_setup'
    try:
        docker('pull', 'nsqio/nsq:v1.3.0')
        image = json.loads(docker('image', 'inspect', 'nsqio/nsq:v1.3.0'))[0]
        digest = next(x for x in image['RepoDigests'] if 'nsq@sha256:' in x)
        report['fixture_image_digest'] = digest; report['fixture_image_id'] = image['Id']
        with tempfile.TemporaryDirectory(prefix=project+'-') as root:
            os.chmod(root, 0o700)
            root = Path(root)
            owned_root = root
            for name in ('deploy.lock', 'ai.lock'):
                (root/name).touch(mode=0o600)
            directory = root/'coordinator'
            binding = {'schema': 'm3-start-boundary/v1', 'operation_id': project,
                       'directory': str(directory), 'scope_sha256': '1'*64, 'protection_sha256': '2'*64,
                       'restore_receipt_sha256': '3'*64, 'source_bundle_sha256': '4'*64,
                       'data_owner': 'isolated-fixture', 'recovery_owner': 'isolated-fixture'}
            binding_sha = hashlib.sha256(_encoded(binding)).hexdigest()
            initialize(directory, binding, binding_sha)
            env = root/'runtime.env'; env.write_bytes(b''); env.chmod(0o600)
            compose = root/'compose.json'
            spec = {'services': {'fixture': {'image': digest, 'command': ['/owned-missing-entrypoint'],
                                             'depends_on': ['unselected'], 'tmpfs': ['/data:size=8388608'],
                                             'mem_limit': '64m', 'cpus': .25, 'restart': 'no'},
                                  'unselected': {'image': digest, 'command': ['/nsqd']}},
                    'networks': {'default': {'internal': True}}}
            def freeze():
                compose.write_bytes(_encoded(spec)); compose.chmod(0o600)
                value = {'schema': 'm3-runtime-start/v1', 'coordinator_binding_sha256': binding_sha,
                         'host': target.socket.gethostname(), 'project': project, 'directory': str(root),
                         'compose_file': str(compose), 'compose_sha256': hashlib.sha256(compose.read_bytes()).hexdigest(),
                         'environment_file': str(env), 'environment_sha256': hashlib.sha256(b'').hexdigest(),
                         'services': ['fixture'], 'images': {'fixture': digest}, 'instances': {'fixture': 1}, 'ai_host': True}
                path = root/'plan.json'; path.write_bytes(_encoded(value)); path.chmod(0o600)
                return target.load(path, hashlib.sha256(path.read_bytes()).hexdigest())
            def check(name, condition):
                if condition is not True: raise BoundaryError('owned target assertion failed')
                report['cases'][name] = True
            starts = []
            report['target_commands'] = []
            command = target.command
            def observed(value, argv, timeout=30):
                kind = next((x for x in ('config', 'up', 'ps', 'inspect') if x in argv), 'unknown')
                row = {'stage': kind, 'returned': False}
                report['target_commands'].append(row)
                if 'up' in argv:
                    check('coordinator_marker_before_actual_up', (directory/'first-runtime-start.json').is_file())
                    starts.append(True)
                result = command(value, argv, timeout)
                row['returned'] = True
                return result
            try:
                with patch.object(cutover_step, 'GLOBAL_LOCK', root/'deploy.lock'), patch.object(cutover_step, 'AI_LOCK', root/'ai.lock'), patch.object(target, 'command', side_effect=observed):
                    plan = freeze()
                    with Boundary(directory, binding_sha) as operation:
                        stage = 'expected_failed_start'
                        try:
                            operation.start('failed-new-runtime', lambda: target.execute(plan))
                        except BoundaryError:
                            check('actual_failed_up_retains_start_barrier', operation.status()['phase'] == 'runtime_start_failed')
                        else: raise BoundaryError('bad fixture runtime unexpectedly started')
                        forbidden = []
                        try: operation.restore_before_start('old-full-backup', lambda: forbidden.append(True))
                        except BoundaryError: check('failed_new_runtime_forbids_old_backup', not forbidden)
                        else: raise BoundaryError('old restore crossed first-start boundary')
                        spec['services']['fixture']['command'] = ['/nsqd', '--data-path=/data', '--mem-queue-size=2']
                        plan = freeze()
                        approval = hashlib.sha256(_encoded(plan)).hexdigest()
                        stage = 'explicit_forward_repair'
                        operation.forward_repair('compatible-fixed-runtime', approval, lambda: target.execute(plan))
                        check('explicit_forward_repair_actual_running_readback', operation.status()['phase'] == 'forward_repair_returned')
                        check('forward_repair_keeps_irreversible_boundary', not operation.status()['old_data_restore_eligible'])
                    auxiliary = docker('ps', '-aq', '--filter', 'label=com.docker.compose.project='+project,
                                       '--filter', 'label=com.docker.compose.service=unselected')
                    check('no_deps_does_not_start_unselected_service', not auxiliary.strip())
                    before_count = len(starts)
                    with cutover_step.deployment_locks(True):
                        try: target.execute(plan)
                        except BlockingIOError: check('original_target_deploy_lock_excludes_start', len(starts) == before_count)
                        else: raise BoundaryError('target lock not reused')
                    for kind in ('image', 'instances'):
                        altered = dict(plan)
                        if kind == 'image': altered['images'] = {'fixture': 'isolated/wrong@sha256:'+'5'*64}
                        else: altered['instances'] = {'fixture': 2}
                        try: target.execute(altered)
                        except BoundaryError: check('configured_'+kind+'_conflict_before_up', len(starts) == before_count)
                        else: raise BoundaryError('conflicting target configuration accepted')
                    check('only_failed_start_and_reviewed_repair_issued', len(starts) == 2)
            finally:
                if plan is not None:
                    # Only bounded state of this known empty fixture, no env/logs/body.
                    ids = docker('ps', '-aq', '--filter', 'label=com.docker.compose.project='+project).decode().split()
                    observed_state = []
                    for identity in ids[:2]:
                        template = '{{json .State.Status}} {{.State.Running}} {{.State.ExitCode}}'
                        state = docker('inspect', '--format', template, identity).decode().split()
                        if (len(state) == 3 and state[0] in {'"created"', '"running"', '"exited"', '"dead"', '"restarting"', '"paused"'}
                                and state[1] in {'true', 'false'} and re.fullmatch('[0-9]{1,5}', state[2])):
                            observed_state.append({'status': json.loads(state[0]), 'running': state[1] == 'true', 'exit_code': int(state[2])})
                    report['owned_fixture_state_before_cleanup'] = observed_state
                    result = subprocess.run(target.compose(plan, 'down', '--volumes', '--remove-orphans'), capture_output=True, timeout=90)
                    down_ok = result.returncode == 0
    except Exception as error:
        report['failure'] = 'owned_target_start_fixture_failed'
        report['failure_stage'] = stage
        codes = {'target command failed; preserve coordinator evidence': 'target_command_nonzero_or_output_cap',
                 'target container readback unavailable': 'container_readback_shape',
                 'target runtime readback differs': 'container_readback_identity_or_health',
                 'target service instance set differs': 'compose_service_id_set',
                 'target runtime instance budget differs': 'readback_instance_budget',
                 'target configured instance budget differs': 'configured_instance_budget',
                 'target image is not the frozen runtime': 'configured_image'}
        report['failure_code'] = codes.get(str(error), 'unclassified_fixed_fixture_failure')
        report['failed'] += 1
    finally:
        owned = docker('ps', '-aq', '--filter', 'label=com.docker.compose.project='+project).decode().split()
        networks = docker('network', 'ls', '-q', '--filter', 'label=com.docker.compose.project='+project).decode().split()
        # Rescue only this exact attempt and fail its cleanup gate if necessary.
        for identity in owned: docker('rm', '-f', identity)
        for identity in networks: docker('network', 'rm', identity)
        report['cleanup'] = {'compose_down_succeeded': down_ok, 'no_rescue_needed': not owned and not networks,
                             'private_fixture_directory_removed': owned_root is not None and not owned_root.exists(),
                             'existing_container_id_set_unchanged': set(docker('ps', '-aq').decode().split()) == existing,
                             'existing_network_id_set_unchanged': set(docker('network', 'ls', '-q').decode().split()) == existing_networks}
        report['passed'] = len(report['cases'])
        report['source_clean_after'] = subprocess.check_output(['git', 'status', '--porcelain'], text=True) == ''
        report['harness_sha256'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in (Path(__file__).resolve().relative_to(Path.cwd()),
                                                Path('scripts/rocketmq/runtime_start.py'), Path('scripts/rocketmq/cutover_step.py'),
                                                Path('scripts/rocketmq/start_boundary.py'))}
        if not all(report['cleanup'].values()) or not report['source_clean_before'] or not report['source_clean_after']:
            report['failed'] += 1
        write_private(Path('runtime-start-native.json'), report)
    print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'skipped': 0}))
    return 0 if report['passed'] == 10 and report['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
