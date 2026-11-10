import json
import unittest
from unittest.mock import Mock, patch

from readable_pop_controls import BUFFER_NAMES, SYSTEM_TOPIC, OwnedPopControls, revive_log_records, snapshot, zero


def metrics(*, offset='0', checkpoint='0', timing='0', include_timer=True):
    raw = (BUFFER_NAMES[0] + '{cluster="FangcunMount",node_type="master"} ' + offset + '\n'
           + BUFFER_NAMES[1] + '{cluster="FangcunMount",node_type="master"} ' + checkpoint + '\n')
    if include_timer:
        raw += 'rocketmq_timing_messages{cluster="FangcunMount",topic="' + SYSTEM_TOPIC + '"} ' + timing + '\n'
    return raw


class ReadablePopControlsTest(unittest.TestCase):
    def test_future_checkpoint_prevents_zero_even_with_no_buffer_or_ordinary_inflight(self):
        raw = metrics(timing='2') + 'rocketmq_consumer_inflight_messages{consumer_group="fake"} 0\n'
        value = snapshot(raw, timing_required=True)
        self.assertFalse(zero(value, timing_required=True))
        for change in (dict(offset='1'), dict(checkpoint='1')):
            self.assertFalse(zero(snapshot(metrics(**change), timing_required=True), timing_required=True))
        self.assertTrue(zero(snapshot(metrics(), timing_required=True), timing_required=True))

    def test_missing_timer_is_explicit_baseline_only_not_a_settled_zero(self):
        raw = metrics(include_timer=False)
        value = snapshot(raw, timing_required=False)
        self.assertIsNone(value['timing'])
        self.assertFalse(value['timer_series_present'])
        self.assertTrue(zero(value, timing_required=False))
        self.assertFalse(zero(value, timing_required=True))
        with self.assertRaises(RuntimeError):snapshot(raw, timing_required=True)

    def test_missing_duplicate_nonfinite_fractional_overflow_and_bad_labels_fail_closed(self):
        for raw in ('', metrics().split('\n',1)[1], metrics()+metrics(),
                    metrics().replace('node_type="master"','node_type="master",node_type="slave"'),
                    metrics().replace('node_type="master"','broken'),
                    metrics()+f'rocketmq_timing_messages{{topic="{SYSTEM_TOPIC}"}} 0\n'):
            with self.subTest(raw=raw[:50]),self.assertRaises(RuntimeError):snapshot(raw,timing_required=True)
        for count in ('NaN','Inf','-1','0.5','1e9999999','9223372036854775808'):
            with self.subTest(count=count),self.assertRaises(RuntimeError):snapshot(metrics(timing=count),timing_required=True)

    def test_constructor_is_inert_and_invalid_stage_cannot_read_or_mutate_anything(self):
        run,admin=Mock(),Mock();proof={}
        control=OwnedPopControls(run,admin,'unused','unused',{'routes':[]},proof,Mock())
        run.assert_not_called();admin.assert_not_called()
        for stage,language in [('held','sdk-go'),('closed','sdk-go'),('baseline','unregistered'),('execute','sdk-python')]:
            with self.subTest(stage=stage),self.assertRaises(RuntimeError):control(stage,language)
        run.assert_not_called();admin.assert_not_called()

    def test_revive_trace_matches_only_exact_fixture_routes_and_exports_digests(self):
        route = dict(t='fixture-topic', c='fixture-group', q=2, so=100, pt=1000, bn='broker-a')

        def row(kind, offset, data):
            return f'INFO - reviveQueueId=1, find {kind}, offset:{offset}, raw : ' + json.dumps(data) + '\n'

        ck = row('ck', 1, dict(route, n=2, d=[0, 3]))
        ack = row('ack', 2, dict(route, ao=100))
        batch = row('batch ack', 3, dict(route, aol=[103]))
        outside = row('ck', 4, dict(route, c='unrelated-group', n=1))
        malformed = row('batch ack', 5, dict(route, aol=[99]))
        report = revive_log_records(ck + ck + ack + batch + outside + malformed,
                                    {('fixture-topic', 'fixture-group')})
        self.assertEqual(1, report['malformed_records'])
        self.assertFalse(report['drain_proven'])
        first, second, third = report['records']
        self.assertEqual(['ck', 'ack', 'batch ack'], [row['kind'] for row in report['records']])
        self.assertEqual({first['merge_key_sha256']}, {second['merge_key_sha256'], third['merge_key_sha256']})
        self.assertEqual(first['offset_sha256s'], second['offset_sha256s'] + third['offset_sha256s'])
        serialized = json.dumps(report)
        for raw in ('fixture-topic', 'fixture-group', 'broker-a', 'unrelated-group'):
            self.assertNotIn(raw, serialized)

    def test_diagnostic_never_overrides_failed_confirmation(self):
        settled = snapshot(metrics(), timing_required=True)
        reappeared = snapshot(metrics(timing='2'), timing_required=True)
        proof = {'go': {'held': reappeared}}
        passed = Mock()
        control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, passed, trace_rebound=True)
        control.observed_timer = True
        trace = {'samples': [settled], 'drain_proven': False}
        with patch.object(control, 'read', side_effect=[settled, reappeared]), patch.object(control, 'trace', return_value=trace):
            with patch('readable_pop_controls.time.sleep'):
                with self.assertRaisesRegex(RuntimeError, 'pop_responsibility_reappeared_after_sdk_close'):
                    control('closed', 'sdk-go')
        self.assertEqual(trace, proof['go']['rebound_trace'])
        passed.assert_not_called()

    def test_closed_confirmation_retains_reappearing_responsibility(self):
        settled = snapshot(metrics(), timing_required=True)
        for field in ('offset', 'checkpoint', 'timing'):
            with self.subTest(field=field):
                reappeared = snapshot(metrics(**{field: '1'}), timing_required=True)
                proof = {'go': {'held': snapshot(metrics(timing='2'), timing_required=True)}}
                passed = Mock()
                control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, passed)
                control.observed_timer = True
                with patch.object(control, 'read', side_effect=[settled, reappeared]), patch('readable_pop_controls.time.sleep'):
                    with self.assertRaisesRegex(RuntimeError, 'pop_responsibility_reappeared_after_sdk_close'):
                        control('closed', 'sdk-go')
                self.assertEqual(proof['go']['closed'], settled)
                self.assertEqual(proof['go']['closed_confirmation'], reappeared)
                passed.assert_not_called()
