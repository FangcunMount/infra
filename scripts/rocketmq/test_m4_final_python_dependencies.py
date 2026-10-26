import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from m4_image_rebuild import final_python_dependencies


class FinalPythonDependencyTest(unittest.TestCase):
    def test_actual_once_text_contract_and_offline_image_boundary(self):
        value = dict(sdk='0.4.0', nsq_absent=True, tornado_absent=True, current_imports=True)
        fixture = SimpleNamespace(select=Mock(), once=Mock(return_value=json.dumps(value)))
        self.assertEqual(final_python_dependencies(fixture), value)
        fixture.select.assert_called_once_with('ai')
        self.assertFalse(fixture.once.call_args.kwargs['network'])
        self.assertEqual(fixture.once.call_args.args[0], '/app/.venv/bin/python')

    def test_actual_present_retired_client_or_wrong_sdk_refuses_candidate(self):
        for key, invalid in (('sdk', '0.4.0a4'), ('nsq_absent', False),
                             ('tornado_absent', False), ('current_imports', False)):
            value = dict(sdk='0.4.0', nsq_absent=True, tornado_absent=True, current_imports=True)
            value[key] = invalid
            fixture = SimpleNamespace(select=Mock(), once=Mock(return_value=json.dumps(value)))
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'retired_python_clients'):
                final_python_dependencies(fixture)
