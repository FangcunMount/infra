"""Offline negative publication gates; these do not claim real Broker proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_release import checked_artifacts, checked_report, checked_run, digest


class ReleaseGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'source.go'
        self.source.write_text('source fixture')
        self.sha = 'a'*40
        cases = {f'basic_{i}': True for i in range(33)}
        for text, count in (('real_database_commit_', 6),
                            ('after_real_broker_ack_tcp_loss', 4),
                            ('producer_exit_broker_restart_new_checker', 3)):
            cases.update({f'public_{text}{i}': True for i in range(count)})
        hashes = {'source.go': digest(self.source)}
        native = {'mode': '0600', 'audit': {'records': [1], 'severity': 'critical'},
                  'business_count': 0, 'local_evidence': 'prepared_retained'}
        self.report = {'sdk_sha': self.sha, 'passed': 46, 'failed': 0, 'skipped': 0,
                       'failure': None, 'cases': cases, 'sdk_tracked_sources_clean': True,
                       'cleanup': {'project_containers_remaining': False,
                                   'compose_down_succeeded': True,
                                   'private_fixture_directory_removed': True},
                       'sdk_source_sha256': hashes, 'sdk_api_source_sha256': hashes,
                       'harness_sha256': hashes, 'source_sha256': hashes,
                       'proof': {'finite_sdk_limit': [copy.deepcopy(native), copy.deepcopy(native)]}}

    def check(self, value):
        path = self.root/'report.json'
        path.write_text(json.dumps(value))
        return checked_report(path, self.sha, 46, self.root, self.root)

    def test_rejects_wrong_source_partial_failed_skipped_or_dirty_acceptance(self):
        self.check(self.report)
        for key, bad in (('sdk_sha', 'b'*40), ('passed', 33), ('failed', 1), ('skipped', 1),
                         ('failure', 'network fault'), ('sdk_tracked_sources_clean', False)):
            with self.subTest(key=key):
                report = copy.deepcopy(self.report); report[key] = bad
                with self.assertRaises(ValueError):
                    self.check(report)

    def test_rejects_cleanup_failure_source_drift_and_missing_native_proof(self):
        report = copy.deepcopy(self.report)
        report['cleanup']['private_fixture_directory_removed'] = False
        with self.assertRaises(ValueError):
            self.check(report)
        report = copy.deepcopy(self.report)
        report['proof']['finite_sdk_limit'][0]['audit']['records'] = []
        with self.assertRaises(ValueError):
            self.check(report)
        self.source.write_text('changed after tests')
        with self.assertRaises(ValueError):
            self.check(self.report)

    def test_rejects_source_unbound_assets_and_skipped_installed_tests(self):
        dist = self.root/'dist'; dist.mkdir()
        (dist/'fixture.whl').write_bytes(b'wheel fixture')
        (dist/'fixture.tar.gz').write_bytes(b'sdist fixture')
        review = {'source': self.sha, 'source_tree': 'tree',
                  'assets': {p.name: digest(p) for p in dist.iterdir()}}
        path = self.root/'artifact-review.json'
        path.write_text(json.dumps(review))
        for filename in ('results.xml', 'wheel-results.xml'):
            (self.root/filename).write_text('<testsuites><testsuite tests="1"><testcase/></testsuite></testsuites>')
        checked_artifacts(self.root, self.sha, 'tree')
        (self.root/'wheel-results.xml').write_text('<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>')
        with self.assertRaises(ValueError):
            checked_artifacts(self.root, self.sha, 'tree')
        review['source'] = 'b'*40; path.write_text(json.dumps(review))
        with self.assertRaises(ValueError):
            checked_artifacts(self.root, self.sha, 'tree')

    def test_live_ci_metadata_must_match_candidate_and_have_no_skipped_jobs(self):
        run = {'name': 'SDK checks', 'head_sha': self.sha,
               'status': 'completed', 'conclusion': 'success'}
        with patch('prepare_release.run', return_value=json.dumps(run)):
            with self.assertRaises(ValueError):
                checked_run('FangcunMount/reliable-messaging', '123', 'SDK checks', 'b'*40)
        with patch('prepare_release.run', side_effect=[json.dumps(run), json.dumps(
                {'total_count': 1, 'jobs': [{'conclusion': 'skipped'}]})]):
            with self.assertRaises(ValueError):
                checked_run('FangcunMount/reliable-messaging', '123', 'SDK checks', self.sha)
