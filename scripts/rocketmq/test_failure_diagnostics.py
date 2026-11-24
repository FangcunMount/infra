import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from failure_diagnostics import (
    DockerCommandError, compose_service_states, docker_startup_state, mysql_startup_status,
    startup_internal_description, summarize,
)


class DiagnosticsTest(unittest.TestCase):
    def test_allowlisted_labels_preserve_transport_cause_without_raw_values(self):
        text = ('failed to sync settings: rpc error: code = Internal desc = '
                'stream terminated by RST_STREAM with error code: INTERNAL_ERROR '
                'password=private-credential body=private-wire')
        result = summarize(text)
        self.assertEqual(result['signals']['http2_rst_internal'], 1)
        self.assertEqual(result['signals']['settings'], 1)
        serialized = json.dumps(result)
        self.assertNotIn('private-', serialized)
        self.assertNotIn('password', serialized)
        self.assertNotIn('body=', serialized)

    def test_unknown_text_is_only_hashed_and_input_is_bounded(self):
        result = summarize(b'x' * 2097152)
        self.assertEqual(result['bytes_examined'], 1048576)
        self.assertEqual(result['signals'], {})

    def test_startup_description_redacts_configured_credentials_signatures_and_body(self):
        raw = 'rpc error: code = Internal desc = header invalid password=private-secret signature=' + 'a'*40
        description = startup_internal_description(raw, ['private-secret'])
        self.assertIn('header invalid', description)
        self.assertNotIn('private-secret', description)
        self.assertNotIn('a'*40, description)
        self.assertIsNone(startup_internal_description('code = Internal desc = payload=private-wire', []))


    def test_docker_failure_exposes_allowlisted_evidence_only(self):
        stderr = (b'private-token=' + b'A' * 262144 +
                  b'\nError response from daemon: failed to set up container networking: private-network-name')
        error = DockerCommandError('compose_start', 'nonzero', returncode=1, stderr=stderr)
        self.assertEqual(error.evidence['operation'], 'compose_start')
        self.assertEqual(error.evidence['returncode'], 1)
        self.assertEqual(error.evidence['kind'], 'nonzero')
        self.assertEqual(error.evidence['stderr_signals'], ['network_setup'])
        self.assertEqual(error.evidence['stderr_bytes_examined'], 262144)
        self.assertNotIn('private-', json.dumps(error.evidence))
        self.assertNotIn('private-', str(error))
        self.assertEqual(DockerCommandError('private-argument', 'nonzero').evidence['operation'], 'other')

    def test_compose_status_keeps_only_known_fields_for_owned_fixture_services(self):
        rows = [
            {'Service': 'broker', 'Name': 'private-name', 'Command': 'private-command',
             'State': 'running', 'Health': 'unhealthy', 'ExitCode': 0},
            {'Service': 'mysql', 'State': 'private-state', 'ExitCode': 'private-exit'},
            {'Service': 'private-service', 'State': 'running'},
        ]
        expected = [
            {'service': 'broker', 'state': 'running', 'health': 'unhealthy', 'exit_code': 0},
            {'service': 'mysql', 'state': 'unknown', 'health': None, 'exit_code': None},
        ]
        self.assertEqual(compose_service_states(json.dumps(rows)), expected)
        self.assertEqual(compose_service_states('\n'.join(map(json.dumps, rows))), expected)

    def test_docker_run_preserves_optional_status_and_wraps_required_timeout(self):
        spec = importlib.util.spec_from_file_location('ci_transactions', Path(__file__).with_name('ci-transactions.py'))
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        argv = ['docker', 'compose', 'private-path']
        optional = subprocess.CompletedProcess(argv, 1, '', 'private-output')
        with patch.object(harness.subprocess, 'run', return_value=optional):
            self.assertIs(harness.run(argv, required=False), optional)
            with self.assertRaises(DockerCommandError) as caught:
                harness.run(argv, docker_phase='compose_start')
            self.assertEqual(caught.exception.evidence['operation'], 'compose_start')
            self.assertEqual(caught.exception.evidence['returncode'], 1)
        timeout = subprocess.TimeoutExpired(argv, 1, stderr=b'RemotingTimeoutException private-value')
        with patch.object(harness.subprocess, 'run', side_effect=timeout):
            with self.assertRaises(DockerCommandError) as caught:
                harness.run(argv, docker_phase='broker_get_config')
            self.assertEqual(caught.exception.evidence['operation'], 'broker_get_config')
            self.assertEqual(caught.exception.evidence['kind'], 'timeout')
            self.assertEqual(caught.exception.evidence['stderr_signals'], ['broker_rpc_timeout'])
            self.assertNotIn('private-value', json.dumps(caught.exception.evidence))


    def test_mysql_startup_keeps_standard_codes_but_no_dsn_or_state_error(self):
        state = '{"ExitCode": 1, "OOMKilled": false, "Error": "private-state-error"}'
        log = '[ERROR] [MY-000067] [Server] unknown variable private-option=secret-dsn'
        result = mysql_startup_status(state, log)
        self.assertEqual(result['exit_code'], 1)
        self.assertFalse(result['oom_killed'])
        self.assertEqual(result['logs']['signals'], ['invalid_option'])
        self.assertEqual(result['logs']['error_codes'], ['MY-000067'])
        self.assertNotIn('private-', json.dumps(result))
        self.assertNotIn('secret-dsn', json.dumps(result))

    def test_startup_state_keeps_recent_health_codes_without_probe_output(self):
        state = {
            'ExitCode': 0, 'OOMKilled': False,
            'Health': {'Status': 'unhealthy', 'Log': [
                {'ExitCode': code, 'Output': 'private-probe-output'}
                for code in (99, 137, -1, 1, False, 'private-code')
            ]},
        }
        self.assertEqual(docker_startup_state(json.dumps(state)), {
            'exit_code': 0, 'oom_killed': False, 'health': 'unhealthy',
            'health_exit_codes': [137, -1, 1],
        })
