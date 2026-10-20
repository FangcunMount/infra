import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location("transactions", Path(__file__).with_name("ci-transactions.py"))
transactions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transactions)


class RuntimeParametersTests(unittest.TestCase):
    def test_iam_host_can_use_its_declared_mysql84_compatibility_matrix(self):
        for version in ('8.0.36', '8.0.44'):
            self.assertTrue(transactions.mysql_fixture_supported(version))
        self.assertTrue(transactions.mysql_fixture_supported('8.4.9', iam_host=True))
        self.assertTrue(transactions.mysql_fixture_supported('8.4.9', sdk_api_go=True))
        self.assertFalse(transactions.mysql_fixture_supported('8.4.9'))
        for version in ('9.3.0', '5.7.44', 'unavailable'):
            self.assertFalse(transactions.mysql_fixture_supported(version, iam_host=True))
    def test_only_complete_numeric_allowlist_leaves_private_admin_capture(self):
        output = "initAuthenticationUser = SECRET\n" + "\n".join(
            f"{name:<40} = {value}" for name, value in
            dict(transactions.PARAMETERS, fileReservedTime=48).items())
        self.assertEqual(transactions.broker_parameters(output),
                         dict(transactions.PARAMETERS, fileReservedTime=48))

    def test_missing_or_unreadable_parameter_fails_instead_of_using_default(self):
        with self.assertRaisesRegex(RuntimeError, "parameter missing"):
            transactions.broker_parameters("transactionTimeOut = unknown")




class ImageAcquisitionTests(unittest.TestCase):
    def test_pull_failure_removes_only_owned_private_fixture_and_writes_private_receipt(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            owned = root / 'rocketmq-m2-image-preflight'; owned.mkdir(mode=0o700)
            (owned / 'private').write_text('sensitive fixture input')
            unrelated = root / 'keep'; unrelated.write_text('preserved')
            report = root / 'report.json'
            calls = []
            def command(argv, **kwargs):
                calls.append(argv)
                if argv[1] == 'pull':
                    raise RuntimeError('private registry diagnostic must not escape')
                return SimpleNamespace(stdout='sha256:broker', returncode=int(argv[3] == 'mysql:test'))
            with self.assertRaises(RuntimeError):
                transactions.fixture_images('broker:test', 'mysql:test', owned, 'rocketmq-m2-test', report, command)
            self.assertFalse(owned.exists())
            self.assertEqual(unrelated.read_text(), 'preserved')
            receipt = json.loads(report.read_text())
            self.assertEqual((receipt['passed'], receipt['failed'], receipt['skipped']), (0, 1, 0))
            self.assertTrue(receipt['cleanup']['compose_not_started'])
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('private registry diagnostic', report.read_text())
            self.assertFalse(any('run' in argv or 'rm' in argv for argv in calls))

    def test_cached_images_require_no_pull_or_fixture_mutation(self):
        with tempfile.TemporaryDirectory(prefix='rocketmq-m2-') as directory:
            root = Path(directory)
            calls = []
            def command(argv, **kwargs):
                calls.append(argv)
                return SimpleNamespace(stdout='sha256:fixed', returncode=0)
            self.assertEqual(transactions.fixture_images('broker:test', 'mysql:test', root, 'rocketmq-m2-test', root / 'report.json', command),
                             ('sha256:fixed', 'sha256:fixed'))
            self.assertFalse(any('pull' in argv for argv in calls))
            self.assertFalse((root / 'report.json').exists())


if __name__ == "__main__":
    unittest.main()
