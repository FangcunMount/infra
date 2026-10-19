import json
import unittest

from failure_diagnostics import summarize, startup_internal_description


class DiagnosticsTest(unittest.TestCase):
    def test_allowlisted_labels_preserve_transport_cause_without_raw_values(self):
        text = ('failed to sync settings: rpc error: code = Internal desc = '
                'stream terminated by RST_STREAM with error code: INTERNAL_ERROR '
                'password=private-credential body=private-wire')
        result = summarize(text)
        self.assertEqual(result['signals']['http2_rst_internal'], 1)
        self.assertEqual(result['signals']['settings'], 1)
        serialized = json.dumps(result)
        self.assertNotIn('private-', serialized)
        self.assertNotIn('password', serialized)
        self.assertNotIn('body=', serialized)

    def test_unknown_text_is_only_hashed_and_input_is_bounded(self):
        result = summarize(b'x' * 2097152)
        self.assertEqual(result['bytes_examined'], 1048576)
        self.assertEqual(result['signals'], {})

    def test_startup_description_redacts_configured_credentials_signatures_and_body(self):
        raw = 'rpc error: code = Internal desc = header invalid password=private-secret signature=' + 'a'*40
        description = startup_internal_description(raw, ['private-secret'])
        self.assertIn('header invalid', description)
        self.assertNotIn('private-secret', description)
        self.assertNotIn('a'*40, description)
        self.assertIsNone(startup_internal_description('code = Internal desc = payload=private-wire', []))
