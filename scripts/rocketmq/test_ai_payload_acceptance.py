import json
import unittest
import xml.etree.ElementTree as ET

from ai_payload_acceptance import CASES, FLAGS, TESTS, MARKER, parse_native, validate_mysql_binding


def proof():
    value = dict(cases={k: True for k in CASES}, passed=len(CASES), failed=0, skipped=0,
        rpc_servers=dict(started=10, closed=10), root='original_mysql_sqlalchemy',
        sdk='0.4.0a2', client='5.1.2', python='3.11.16', **{k: True for k in FLAGS})
    suite = ET.Element('testsuite')
    for name in TESTS:
        ET.SubElement(suite, 'testcase', name=name, classname='tests.integration.rocketmq_payload_host')
    return value, suite


def output(value):
    return MARKER + json.dumps(value)


class CurrentPayloadGate(unittest.TestCase):
    def test_complete_exact_receipt_and_test_ids(self):
        value, suite = proof()
        result = parse_native(output(value), ET.tostring(suite))
        self.assertEqual((result['passed'], len(result['receipt']['cases'])), (15, 21))

    def test_partial_or_unclosed_or_different_scope_never_passes(self):
        for damage in ('partial', 'unclosed', 'numeric_bool', 'private', 'duplicate', 'broker'):
            value, suite = proof()
            if damage == 'partial':
                value['cases'].pop(next(iter(CASES)))
                value['passed'] -= 1
            elif damage == 'unclosed':
                value['rpc_servers']['closed'] = 9
            elif damage == 'numeric_bool':
                value['cases'][next(iter(CASES))] = 1
            elif damage == 'private':
                value['private_body'] = 'never export'
            elif damage == 'broker':
                value['broker_transaction_gate_not_claimed'] = False
            raw = output(value)
            if damage == 'duplicate':
                raw += '\n' + raw
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                parse_native(raw, ET.tostring(suite))

    def test_missing_duplicate_skipped_error_or_wrong_class_native_is_rejected(self):
        for damage in ('missing', 'duplicate', 'skipped', 'error', 'failure', 'class'):
            value, suite = proof()
            if damage == 'missing':
                suite.remove(suite[0])
            elif damage == 'duplicate':
                suite[1].set('name', suite[0].get('name'))
            elif damage == 'class':
                suite[0].set('classname', 'legacy_probe')
            else:
                ET.SubElement(suite[0], damage)
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                parse_native(output(value), ET.tostring(suite))

    def test_service_publish_must_be_exact_loopback(self):
        expected = [{'HostIp': '127.0.0.1', 'HostPort': '3306'}]
        self.assertEqual(validate_mysql_binding(json.dumps({'3306/tcp': expected})), expected)
        for selected in (None, [], [{'HostIp': '0.0.0.0', 'HostPort': '3306'}], expected * 2):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                validate_mysql_binding(json.dumps({'3306/tcp': selected}))


if __name__ == '__main__':
    unittest.main()
