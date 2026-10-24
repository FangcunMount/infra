import json
from pathlib import Path
import tempfile
import unittest
from maintenance_composition import ci_guard,go_report,python_report


class MaintenanceComposition(unittest.TestCase):
    def test_ci_guard_precedes_dependency_construction(self):
        good=dict(GITHUB_ACTIONS='true',RUNNER_OS='Linux',RUNNER_ENVIRONMENT='github-hosted')
        ci_guard(good)
        for value in ({},dict(good,RUNNER_ENVIRONMENT='self-hosted'),dict(good,DOCKER_HOST='tcp://remote'),dict(good,DOCKER_CONTEXT='remote')):
            with self.assertRaises(RuntimeError):ci_guard(value)

    def test_go_required_root_and_package_skip_are_not_hidden(self):
        events=[dict(Action='run',Test='TestOriginal'),dict(Action='pass',Test='TestOriginal'),dict(Action='pass')]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'raw'
            path.write_text('\n'.join(json.dumps(e) for e in events))
            self.assertEqual(go_report(path,{'TestOriginal'})['passed'],1)
            for tail in ([dict(Action='skip')],[dict(Action='fail')],[dict(Action='run',Test='TestUnfinished')]):
                path.write_text('\n'.join(json.dumps(e) for e in events+tail))
                with self.assertRaises(RuntimeError):go_report(path,{'TestOriginal'})

    def test_python_eight_cases_and_no_skip_required(self):
        cases=''.join(f'<testcase classname="original" name="test_{i}" />' for i in range(8))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'junit.xml';path.write_text('<testsuites><testsuite>'+cases+'</testsuite></testsuites>')
            self.assertEqual(python_report(path)['passed'],8)
            path.write_text('<testsuites><testsuite>'+cases.replace('/>','><skipped /></testcase>',1)+'</testsuite></testsuites>')
            with self.assertRaises(RuntimeError):python_report(path)
