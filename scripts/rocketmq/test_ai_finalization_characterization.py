import unittest
import xml.etree.ElementTree as ET

from ai_finalization_characterization import RECOVERY_TESTS, TESTS, diagnostics, parse_native


def suite(names=TESTS):
    root = ET.Element('testsuite')
    for name in sorted(names):
        ET.SubElement(root, 'testcase', name=name,
            classname='tests.integration.test_finalization_characterization')
    return root


class CharacterizationReceiptTest(unittest.TestCase):
    def test_exact_nonempty_receipt_is_explicitly_known_gap_only(self):
        receipt = parse_native(ET.tostring(suite()))
        self.assertEqual(receipt['passed'], 2)
        self.assertTrue(receipt['known_recovery_gap_reproduced'])

    def test_empty_missing_duplicate_and_unlisted_are_rejected(self):
        for names in ([], [next(iter(TESTS))], ['unlisted', 'other'],
                      [next(iter(TESTS))] * 2):
            with self.subTest(count=len(names)), self.assertRaises(ValueError):
                parse_native(ET.tostring(suite(names)))

    def test_failure_teardown_error_and_skip_are_not_success(self):
        for tag in ('failure', 'error', 'skipped'):
            root = suite()
            ET.SubElement(root[0], tag).text = 'private credential/body must stay private'
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                parse_native(ET.tostring(root))

    def test_diagnostics_export_classes_without_sensitive_trace_values(self):
        root = suite()
        ET.SubElement(root[0], 'error').text = 'ValueError: private credential/body'
        rows = diagnostics(ET.tostring(root))
        self.assertEqual(rows[0]['error_classes'], ['ValueError'])
        self.assertNotIn('private', str(rows))


class RecoveryReceiptTest(unittest.TestCase):
    def suite(self):
        root = ET.Element('testsuite')
        for name, classname in RECOVERY_TESTS.items():
            ET.SubElement(root, 'testcase', name=name, classname=classname)
        return root

    def test_exact_recovery_set_cannot_be_confused_with_old_characterization(self):
        raw = ET.tostring(self.suite())
        receipt = parse_native(raw, recovery=True)
        self.assertEqual(receipt['passed'], 20)
        self.assertTrue(receipt['current_protocol_recovery_verified'])
        self.assertFalse(receipt['known_recovery_gap_reproduced'])
        with self.assertRaises(ValueError):
            parse_native(raw)
        with self.assertRaises(ValueError):
            parse_native(ET.tostring(suite()), recovery=True)

    def test_missing_wrong_class_and_failure_are_rejected(self):
        for damage in ('missing', 'class', 'failure', 'error', 'skipped', 'duplicate'):
            root = self.suite()
            if damage == 'missing':
                root.remove(root[0])
            elif damage == 'class':
                root[0].set('classname', 'another.test')
            elif damage == 'duplicate':
                root[1].set('name', root[0].get('name'))
            else:
                ET.SubElement(root[0], damage).text = 'private body'
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                parse_native(ET.tostring(root), recovery=True)

    def test_recovery_diagnostics_keep_only_known_test_ids_and_classes(self):
        root = self.suite()
        ET.SubElement(root[0], 'error').text = 'ValueError: private response/credential'
        rows = diagnostics(ET.tostring(root), recovery=True)
        self.assertEqual(rows[0]['test'], root[0].get('name'))
        self.assertNotIn('private', str(rows))


if __name__ == '__main__':
    unittest.main()
