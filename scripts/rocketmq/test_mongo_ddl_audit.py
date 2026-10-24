import copy
import json
import unittest

from mongo_ddl_audit import CONTROL, FILTER, install, read


class MongoDDLAuditTest(unittest.TestCase):
    def fixture(self):
        return dict(status={'was': 1, 'filter': FILTER}, rows=[
            dict(kind=kind, collection=CONTROL, client='127.0.0.1:1234', error_code=0)
            for kind in ('create', 'drop', 'create', 'drop')])

    def parse(self, value):
        return read(lambda _: json.dumps(value), 'qs_m3_image_start_aabbccddeeff')

    def test_positive_controls_do_not_hide_application_ddl(self):
        value = self.fixture()
        value['rows'].append(dict(kind='createIndexes', collection='answersheets', client='172.18.0.4:1234', error_code=13))
        actual = self.parse(value)
        self.assertEqual(actual['attempts'], 1)
        self.assertEqual(actual['commands'][0]['error_code'], 13)
        self.assertEqual(actual['positive_controls'], 4)
        self.assertFalse(actual['command_bodies_exported'])

    def test_lost_controls_or_changed_filter_fail_closed(self):
        for change in ('lost', 'filter', 'level', 'control_error'):
            value = copy.deepcopy(self.fixture())
            if change == 'lost': value['rows'].pop()
            if change == 'filter': value['status']['filter'] = {}
            if change == 'level': value['status']['was'] = 0
            if change == 'control_error': value['rows'][0]['error_code'] = 13
            with self.assertRaises(RuntimeError): self.parse(value)

    def test_setup_requires_owned_database_and_precreates_capped_profile(self):
        calls = []
        install(calls.append, 'qs_m3_image_start_aabbccddeeff')
        self.assertLess(calls[0].index('createCollection("system.profile"'), calls[0].index('setProfilingLevel'))
        with self.assertRaises(RuntimeError): install(calls.append, 'production')
        with self.assertRaises(RuntimeError): read(calls.append, 'production')

    def test_unexpected_command_data_is_rejected(self):
        value = self.fixture()
        value['rows'].append(dict(kind='create', collection='unsafe body\n', client='', error_code=0))
        with self.assertRaises(RuntimeError): self.parse(value)


if __name__ == '__main__': unittest.main()
