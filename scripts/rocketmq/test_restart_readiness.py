"""Strict startup retry gates only; real restart proofs remain required CI."""
import json
import unittest
from unittest.mock import patch

from sdk_faults import recover_after_restart


class Attempt:
    def __init__(self, code=None, commits=0):
        self.code = code
        self.closed = False
        self.events = [{'event':'failure_code','decision':code},
                       {'event':'closed','decision':'failed_start_drained'},
                       {'event':'metrics','decision':json.dumps({'CheckCommit':commits})}]
        self.process = type('Process', (), {'pid':123})()

    def wait(self, event, **kwargs):
        if event != 'ready':
            raise AssertionError('startup retry attempted a business operation')
        if self.code:
            raise RuntimeError('fixture startup refused')

    def finish(self, expected):
        if expected != 1:
            raise AssertionError('failed startup was counted as success')

    def close(self):
        self.closed = True
        return True


class RestartReadinessTest(unittest.TestCase):
    @patch('sdk_faults.time.sleep')
    def test_only_idle_topic_not_found_retried_and_actual_prior_checks_retained(self, _sleep):
        failed, ready = Attempt('rocketmq_40402', commits=3), Attempt()
        attempts = iter((failed, ready))
        calls = []
        def start(language, mode, **kwargs):
            calls.append((language, mode, kwargs)); return next(attempts)
        actual, proof = recover_after_restart(start, 'sdk-go', 'mongo')
        self.assertIs(actual, ready)
        self.assertEqual(proof['commit_checks_before_ready'], 3)
        self.assertTrue(failed.closed)
        self.assertEqual(calls, [('sdk-go','recover',{'storage':'mongo'})]*2)

    def test_authorization_refusal_is_not_hidden_by_restart_retries(self):
        calls = []
        def start(*args, **kwargs):
            calls.append(args); return Attempt('rocketmq_40300')
        with self.assertRaises(RuntimeError):
            recover_after_restart(start, 'sdk-go', 'mongo')
        self.assertEqual(len(calls), 1)

    @patch('sdk_faults.time.sleep')
    def test_persistent_missing_topic_fails_after_bounded_idle_start_attempts(self, _sleep):
        attempts = []
        def start(*args, **kwargs):
            attempt = Attempt('half_rejected_40402'); attempts.append(attempt); return attempt
        with self.assertRaisesRegex(RuntimeError, 'did not become ready'):
            recover_after_restart(start, 'sdk-python', 'mysql')
        self.assertEqual(len(attempts), 6)
        self.assertTrue(all(a.closed for a in attempts))
