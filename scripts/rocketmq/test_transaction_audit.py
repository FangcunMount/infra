import json
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit_transaction_limit import main, parse_index, write_private, TOPIC


class AuditTest(unittest.TestCase):
    def test_cli_native_evidence_emits_safe_critical_alarm_and_exit_two(self):
        identity = 'A' * 32
        report = parse_index(f'{identity} 0 12 123@{TOPIC}@K@fixture@{identity}@456', 'fixture')
        output = io.StringIO()
        with patch('sys.argv', ['audit', '--container', 'fixture-broker', '--project',
                               'fixture', '--key', 'fixture', '--output', '/tmp/audit.json']), \
                patch('audit_transaction_limit.export', return_value=report) as export, \
                contextlib.redirect_stdout(output):
            self.assertEqual(main(), 2)
        export.assert_called_once_with('fixture-broker', 'fixture', 'fixture', Path('/tmp/audit.json'))
        emitted = json.loads(output.getvalue())
        self.assertEqual(emitted, {'records': 1, 'read_only': True, 'body_exported': False,
                                  'truncated_possible': False,
                                  'alert': 'native_transaction_check_limit_reached',
                                  'severity': 'critical'})

    def test_extract_only_allowlisted_index_not_arbitrary_admin_or_body(self):
        identity = 'A' * 32
        raw = f'private diagnostic credential=never-export\n{identity} 0 12 123@{TOPIC}@K@fixture@{identity}@456\nbody=never-export'
        report = parse_index(raw,'fixture')
        encoded = json.dumps(report)
        self.assertNotIn('never-export',encoded)
        self.assertNotIn('credential',encoded)
        self.assertEqual(report['records'][0]['commitlog_offset'],456)
        self.assertEqual(report['alert'],'native_transaction_check_limit_reached')
        self.assertEqual(report['severity'],'critical')
        self.assertIsNone(parse_index('', 'fixture')['alert'])
        with self.assertRaises(RuntimeError):
            parse_index(raw.replace('@fixture@','@different@'),'fixture')

    def test_private_create_does_not_replace_or_follow_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'audit.json'
            write_private(path,{'records':[]})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):
                write_private(path,{'overwritten':True})
