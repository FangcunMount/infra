"""Native acceptance stays complete but cannot be doubled by a PR event."""
from pathlib import Path
from fnmatch import fnmatchcase
import unittest

import yaml


class ReadableCIPolicyTest(unittest.TestCase):
    def test_isolated_fixture_changes_do_not_launch_unrelated_sdk_matrices_but_core_changes_do(self):
        root=Path(__file__).resolve().parents[2]
        def selected(patterns,path):
            enabled=False
            for pattern in patterns:
                if fnmatchcase(path,pattern.removeprefix('!')):enabled=not pattern.startswith('!')
            return enabled
        for filename in ('rocketmq.yml','rocketmq-sdk.yml','rocketmq-faults.yml','rocketmq-limits.yml',
                         'rocketmq-m3-resources.yml','rocketmq-readable-routes.yml'):
            value=yaml.safe_load((root/'.github/workflows'/filename).read_text())
            events=value.get('on',value.get(True))
            self.assertIn('workflow_dispatch',events)
            for event in ('pull_request','push'):
                if event not in events:continue
                patterns=events[event]['paths']
                for path in ('scripts/rocketmq/qs_replan_acceptance.py',
                             'scripts/rocketmq/image_fixtures/readable_replan_test.go',
                             'scripts/rocketmq/readable_publish_candidates.py',
                             'scripts/rocketmq/readable_cutover_materials.py'):
                    with self.subTest(file=filename,event=event,path=path):self.assertFalse(selected(patterns,path))
                for path in ('scripts/rocketmq/ci-transactions.py','scripts/rocketmq/qs_evaluation_acceptance.py',
                             'scripts/rocketmq/new_unknown_shared_helper.py','components/rocketmq/docker-compose.yml',
                             '.github/workflows/'+filename):
                    with self.subTest(file=filename,event=event,path=path):self.assertTrue(selected(patterns,path))
        contracts=yaml.safe_load((root/'.github/workflows/rocketmq-contracts.yml').read_text())
        events=contracts.get('on',contracts.get(True))
        self.assertTrue(selected(events['pull_request']['paths'],'scripts/rocketmq/qs_replan_acceptance.py'))
        command=contracts['jobs']['contracts']['steps'][-1]['run']
        self.assertIn("-p 'test_*.py'",command)
        self.assertNotIn('docker',command)

    def test_replan_requires_manual_native_entry_and_keeps_both_required_profiles(self):
        root=Path(__file__).resolve().parents[2]
        value=yaml.safe_load((root/'.github/workflows/rocketmq-readable-replan.yml').read_text())
        jobs=value['jobs'];native=jobs['business']
        self.assertEqual(native['if'],"github.event_name == 'workflow_dispatch'")
        self.assertEqual(native['needs'],'contracts')
        self.assertNotIn('if',jobs['contracts'])
        self.assertIs(native['strategy']['fail-fast'],False)
        self.assertEqual(native['strategy']['matrix']['mysql'],['mysql:8.0.36','mysql:8.4'])
        command=next(s['run'] for s in native['steps'] if s.get('name')=='Actual host original root under readable routes')
        self.assertIn("data['passed']==len(data['cases'])==14",command)
        self.assertIn("replan['native_receipt']['passed']==5",command)
        self.assertIn("data['failed']==data['skipped']==0",command)
