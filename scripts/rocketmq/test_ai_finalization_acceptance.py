import json
import unittest
import xml.etree.ElementTree as ET

from ai_finalization_acceptance import CASES, TESTS, finalization_manifest, parse_receipt, read_receipt
from ai_admission_acceptance import host_failure_diagnostics
from ai_finalization_characterization import diagnostics
from routes import validate_v2


def proof():
    value = dict(cases={k: True for k in CASES}, passed=len(CASES), failed=0, skipped=0,
        root='original_mysql_sqlalchemy', sdk='0.4.0a2', client='5.1.2', python='3.11.16',
        system_login_not_claimed=True, paired_qs_business_not_claimed=True,
        real_external_provider_not_claimed=True, database_commit_network_fault_not_claimed=True,
        real_packet_fault_verified=True, five_path_matrix_verified=True,
        real_http_counter_verified=True, process_sigkill_verified=True)
    root = ET.Element('testsuite')
    for name in TESTS:
        ET.SubElement(root, 'testcase', name=name)
    return value, root


def output(value):
    return 'M3_AI_FINALIZATION_RECEIPT ' + json.dumps(value)


class FinalizationHostProof(unittest.TestCase):
    def test_matrix_fixture_failures_keep_only_source_locations_and_exception_classes(self):
        name = sorted(TESTS)[0]
        value = ET.Element('testsuite')
        case = ET.SubElement(value, 'testcase', name=name)
        ET.SubElement(case, 'error').text = ('tests/integration/test_evaluation_step.py:53\n'
            'sqlalchemy.exc.IntegrityError: password=never-export wire=private-fixture')
        actual = diagnostics(ET.tostring(value), tests=TESTS)
        self.assertEqual(actual, [dict(test=name, statuses=['error'],
            error_classes=['sqlalchemy.exc.IntegrityError'],
            source_locations=['tests/integration/test_evaluation_step.py:53'])])
        raw = f'ERROR tests/integration/rocketmq_finalization_host.py::{name}\nrocketmq_finalization_matrix.py:42\nwire=never-export'
        self.assertEqual(host_failure_diagnostics(raw,
            ('rocketmq_finalization_host.py', 'rocketmq_finalization_matrix.py'), TESTS),
            dict(failed_cases=[name], assertion_lines=[42]))

    def test_exact_manifest_and_nonempty_receipt(self):
        validate_v2(finalization_manifest())
        value, root = proof()
        self.assertEqual(parse_receipt(output(value), ET.tostring(root))['passed'], 32)

    def test_old_state_or_partial_proof_is_not_new_process_acceptance(self):
        value, root = proof()
        for damage in ('old_marker', 'missing', 'http', 'kill', 'packet', 'matrix', 'duplicate'):
            changed = json.loads(json.dumps(value))
            text = output(changed)
            if damage == 'old_marker':
                text = text.replace('FINALIZATION', 'STATE')
            elif damage == 'duplicate':
                text += '\n' + text
            else:
                if damage == 'missing':
                    changed['cases'].pop(next(iter(CASES)))
                    changed['passed'] -= 1
                else:
                    changed[{'http':'real_http_counter_verified', 'kill':'process_sigkill_verified', 'packet':'real_packet_fault_verified',
                             'matrix':'five_path_matrix_verified'}[damage]] = False
                text = output(changed)
            with self.subTest(damage=damage), self.assertRaises(RuntimeError):
                parse_receipt(text, ET.tostring(root))

    def test_skip_teardown_error_and_missing_native_are_rejected(self):
        for damage in ('skipped', 'error', 'failure', 'missing'):
            value, root = proof()
            if damage == 'missing':
                root.remove(root[0])
            else:
                ET.SubElement(root[0], damage)
            with self.subTest(damage=damage), self.assertRaises(RuntimeError):
                parse_receipt(output(value), ET.tostring(root))

    def test_unknown_fields_are_not_exported(self):
        value, _ = proof()
        value['private_body'] = 'never export'
        self.assertIsNone(read_receipt(output(value)))


if __name__ == '__main__':
    unittest.main()
