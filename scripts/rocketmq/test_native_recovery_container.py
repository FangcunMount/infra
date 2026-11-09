import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import native_recovery_container as runner
from start_boundary import BoundaryError, _encoded, _publish


class NativeRecoveryContainerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.operation = root / 'operation'
        self.inputs = root / 'inputs'
        self.java = self.inputs / 'java'
        for path in (self.operation, self.inputs, self.java, self.java / 'tls'):
            path.mkdir(mode=0o700)
        self.fd = os.open(self.operation, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        hashes = {key: self.write(self.inputs / (key + '.json')) for key in runner.INPUTS}
        self.plan = {
            'schema': 'm3-native-recovery-container/v1', 'command': 'recover',
            'directory': str(self.operation), 'host': socket.gethostname(),
            'image_id': 'sha256:' + '1' * 64, 'source_sha': 'a' * 40,
            'network_id': '2' * 64, 'network_name': 'owned-fixture', 'binding_sha256': '3' * 64,
            'step': 'recover-original', 'inputs': hashes,
            'java': {'tools': self.write(self.java / 'tools.yml'), 'ca': self.write(self.java / 'tls' / 'server.crt')},
        }
        self.step_sha = '4' * 64
        self.cid = '5' * 64
        self.env = {
            'M3_COORDINATOR_DIRECTORY': str(self.operation),
            'M3_COORDINATOR_BINDING_SHA256': self.plan['binding_sha256'],
            'M3_COORDINATOR_STEP': self.plan['step'], 'M3_COORDINATOR_STEP_PLAN_SHA256': self.step_sha,
        }

    def write(self, path):
        path.write_bytes(b'fixture\n')
        path.chmod(0o600)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run_container(self, step_sha=None, plan=None):
        runner.run_container(self.fd, plan or self.plan, self.operation, self.inputs, self.java,
                             step_sha or self.step_sha, ['recover'], (), time.monotonic() + 230)

    def terminal(self, step_sha, cid, code):
        return dict(Id=cid, Name='/native-container-' + step_sha, Image=self.plan['image_id'], RestartCount=0,
                    Config={'Labels': {'native.recovery.step': step_sha}},
                    NetworkSettings={'Networks': {'fixture': {'NetworkID': self.plan['network_id']}}},
                    State=dict(Status='exited', Running=False, ExitCode=code, OOMKilled=False,
                               StartedAt='2026-01-01T00:00:00Z', FinishedAt='2026-01-01T00:00:01Z'))

    def test_plan_builds_only_fixed_command_and_mounts(self):
        directory, material, java, step_sha, cli = runner.arguments(self.plan, self.env)
        self.assertEqual(step_sha, self.step_sha)
        protected = (self.operation / 'state.json',)
        cmd = runner.create_args(self.plan, directory, material, java, 'named', cli, protected)
        self.assertEqual(cmd[cmd.index('--network') + 1], self.plan['network_id'])
        self.assertEqual(cmd[cmd.index('--user') + 1], '3000:3000')
        self.assertIn('--read-only', cmd)
        self.assertNotIn('--rm', cmd)
        self.assertIn(f'type=bind,src={protected[0]},dst={protected[0]},readonly', cmd)
        self.assertIn('/usr/bin/timeout', cmd)
        self.assertIn('195s', cmd)
        self.assertEqual(cli[0], 'recover')

    def test_plan_refuses_mismatched_coordinator_extra_mount_material_and_digest(self):
        with self.assertRaises(BoundaryError):
            runner.arguments(self.plan, self.env | {'M3_COORDINATOR_STEP': 'other'})
        extra = self.java / 'extra'
        self.write(extra)
        with self.assertRaises(BoundaryError):
            runner.arguments(self.plan, self.env)
        extra.unlink()
        (self.inputs / 'approval.json').write_text('changed')
        with self.assertRaises(BoundaryError):
            runner.arguments(self.plan, self.env)

    def test_requires_live_lock_and_matching_reviewed_step(self):
        binding = self.plan['binding_sha256']
        step = dict(directory=str(self.operation), binding_sha256=binding, host=self.plan['host'],
                    step=self.plan['step'], timeout_seconds=240, kind='runtime-start')
        step_sha = hashlib.sha256(_encoded(step)).hexdigest()
        _publish(self.fd, 'reviewed-step-' + step_sha + '.json', step)
        _publish(self.fd, 'binding.json', {})
        _publish(self.fd, 'first-runtime-start.json', {})
        _publish(self.fd, 'state.json', dict(binding_sha256=binding, step=self.plan['step'], phase='runtime_start_issued'))
        with self.assertRaises(BoundaryError):
            runner.require_issued(self.fd, self.plan, self.operation, step_sha)
        owner = os.open(self.operation, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, owner)
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        protected = runner.require_issued(self.fd, self.plan, self.operation, step_sha)
        self.assertIn(self.operation / 'state.json', protected)
        with self.assertRaises(BoundaryError):
            runner.require_issued(self.fd, self.plan | {'step': 'different'}, self.operation, step_sha)
        with self.assertRaises(BoundaryError):
            runner.require_issued(self.fd, self.plan | {'prior_terminal': {}}, self.operation, step_sha)

    def test_timeout_retains_identity_and_refuses_a_second_launch(self):
        with patch.object(runner, 'docker', side_effect=[self.cid, '', subprocess.TimeoutExpired('wait', 1)]) as daemon:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_container()
            self.assertEqual(daemon.call_args_list[1].args[0], ['start', self.cid])
            with self.assertRaisesRegex(BoundaryError, 'exit is unknown'):
                self.run_container('6' * 64, self.plan | {'inputs': self.plan['inputs'] | {'request': '7' * 64}})
            self.assertEqual(daemon.call_count, 3)
        prefix = self.operation / ('native-container-' + self.step_sha)
        self.assertEqual(json.loads(prefix.with_name(prefix.name + '-created.json').read_bytes()), {'container_id': self.cid})
        self.assertFalse(prefix.with_name(prefix.name + '-exit.json').exists())

    def test_insufficient_budget_refuses_before_issuing_container(self):
        with patch.object(runner, 'docker') as daemon:
            with self.assertRaisesRegex(BoundaryError, 'insufficient budget'):
                runner.run_container(self.fd, self.plan, self.operation, self.inputs, self.java,
                                     self.step_sha, ['recover'], (), time.monotonic() + 200)
            daemon.assert_not_called()
        self.assertEqual(list(self.operation.iterdir()), [])

    def test_success_requires_inspected_terminal_identity_and_no_retry(self):
        name = 'native-container-' + self.step_sha
        terminal = self.terminal(self.step_sha, self.cid, 0)
        with patch.object(runner, 'docker', side_effect=[self.cid, '', '0', json.dumps([terminal])]) as daemon:
            self.run_container()
            self.assertEqual(daemon.call_args_list[-1].args[0], ['container', 'inspect', self.cid])
            with self.assertRaises(FileExistsError):
                self.run_container()
            self.assertEqual(daemon.call_count, 4)
        result = json.loads((self.operation / (name + '-exit.json')).read_bytes())
        self.assertEqual(result, dict(container_id=self.cid, exit_code=0, oom_killed=False,
                                      started_at=terminal['State']['StartedAt'], finished_at=terminal['State']['FinishedAt']))

    def test_unknown_exit_handoff_requires_new_request_and_independent_observation(self):
        with patch.object(runner, 'docker', side_effect=[self.cid, '', subprocess.TimeoutExpired('wait', 1)]):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_container()
        old_name = 'native-container-' + self.step_sha
        previous = json.dumps([self.terminal(self.step_sha, self.cid, 124)])
        paths_before = sorted(self.operation.iterdir())
        with patch.object(runner, 'docker', return_value=previous):
            observation = runner.terminal_observation(self.fd, old_name)
        self.assertEqual(sorted(self.operation.iterdir()), paths_before)
        self.assertFalse(observation['execution_authorized'])
        approval = {'step_plan_sha256': self.step_sha,
                    'observation_sha256': hashlib.sha256(_encoded(observation)).hexdigest()}
        new_step, new_cid = '6' * 64, '8' * 64
        new_plan = self.plan | {'prior_terminal': approval}
        with patch.object(runner, 'docker') as daemon:
            with self.assertRaisesRegex(BoundaryError, 'new request'):
                self.run_container(new_step, new_plan)
            daemon.assert_not_called()
        new_plan['inputs'] = self.plan['inputs'] | {'request': '7' * 64}
        with patch.object(runner, 'docker', return_value=previous):
            with self.assertRaisesRegex(BoundaryError, 'observation differs'):
                self.run_container(new_step, new_plan | {'prior_terminal': approval | {'observation_sha256': '0' * 64}})
        next_exit = json.dumps([self.terminal(new_step, new_cid, 0)])
        with patch.object(runner, 'docker', side_effect=[previous, new_cid, '', '0', next_exit]):
            self.run_container(new_step, new_plan)
        self.assertFalse((self.operation / (old_name + '-exit.json')).exists())
        self.assertEqual(json.loads((self.operation / (old_name + '-reconciled.json')).read_bytes()),
                         {'terminal': observation['terminal'], 'observation_sha256': approval['observation_sha256'],
                          'reviewed_by_step_plan_sha256': new_step})

    def test_prior_observation_refuses_running_or_mismatched_container(self):
        name = 'native-container-' + self.step_sha
        for changed in (
                {'Id': '6' * 64},
                {'Config': {'Labels': {'native.recovery.step': '7' * 64}}},
                {'NetworkSettings': {'Networks': {'wrong': {'NetworkID': '8' * 64}}}},
                {'State': {'Status': 'running', 'Running': True}}):
            with self.subTest(changed=changed), patch.object(runner, 'docker', return_value=json.dumps([
                    self.terminal(self.step_sha, self.cid, 0) | changed])):
                with self.assertRaisesRegex(BoundaryError, 'terminal state unknown'):
                    runner.inspect_exit(self.cid, name, self.plan['image_id'], self.plan['network_id'])
