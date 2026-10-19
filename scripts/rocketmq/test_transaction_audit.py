import json
from pathlib import Path
import tempfile
import unittest

from audit_transaction_limit import parse_index, write_private, TOPIC


class AuditTest(unittest.TestCase):
    def test_extract_only_allowlisted_index_not_arbitrary_admin_or_body(self):
        identity = 'A' * 32
        raw = f'private diagnostic credential=never-export\n{identity} 0 12 123@{TOPIC}@K@fixture@{identity}@456\nbody=never-export'
        report = parse_index(raw,'fixture')
        encoded = json.dumps(report)
        self.assertNotIn('never-export',encoded)
        self.assertNotIn('credential',encoded)
        self.assertEqual(report['records'][0]['commitlog_offset'],456)
        with self.assertRaises(RuntimeError):
            parse_index(raw.replace('@fixture@','@different@'),'fixture')

    def test_private_create_does_not_replace_or_follow_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'audit.json'
            write_private(path,{'records':[]})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):
                write_private(path,{'overwritten':True})
