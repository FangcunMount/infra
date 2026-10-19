import importlib.util
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
