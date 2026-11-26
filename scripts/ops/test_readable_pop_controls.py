import unittest
from unittest.mock import Mock, patch

from readable_pop_controls import BUFFER_NAMES, REVIVE_LAG_NAME, SYSTEM_TOPIC, OwnedPopControls, snapshot, zero


def metrics(*, offset='0', checkpoint='0', timing='0', include_timer=True):
    raw = (BUFFER_NAMES[0] + '{cluster="FangcunMount",node_type="master"} ' + offset + '\n'
           + BUFFER_NAMES[1] + '{cluster="FangcunMount",node_type="master"} ' + checkpoint + '\n')
    if include_timer:
        raw += 'rocketmq_timing_messages{cluster="FangcunMount",topic="' + SYSTEM_TOPIC + '"} ' + timing + '\n'
    return raw


def metrics_with_revive_lag(lag='0', **values):
    queues = ''.join(f'{REVIVE_LAG_NAME}{{queue_id="{queue}"}} {lag if queue == 2 else "0"}\n'
                     for queue in range(8))
    return metrics(**values) + queues


class ReadablePopControlsTest(unittest.TestCase):
    def test_future_checkpoint_prevents_zero_even_with_no_buffer_or_ordinary_inflight(self):
        raw = metrics(timing='2') + 'rocketmq_consumer_inflight_messages{consumer_group="fake"} 0\n'
        value = snapshot(raw, timing_required=True)
        self.assertFalse(zero(value, timing_required=True))
        for change in (dict(offset='1'), dict(checkpoint='1')):
            self.assertFalse(zero(snapshot(metrics(**change), timing_required=True), timing_required=True))
        self.assertTrue(zero(snapshot(metrics(), timing_required=True), timing_required=True))

    def test_candidate_requires_all_eight_unique_revive_queues(self):
        lines = [f'{REVIVE_LAG_NAME}{{queue_id="{queue}"}} 0\n' for queue in range(8)]
        raw = metrics() + ''.join(lines)
        self.assertTrue(zero(snapshot(raw, timing_required=True, revive_required=True), timing_required=True))
        for altered in (lines[:-1], lines[:-1] + [lines[0]], lines[:-1] + [lines[-1].replace('"7"', '"8"')]):
            with self.subTest(altered=altered), self.assertRaisesRegex(
                    RuntimeError, 'complete_unique_revive_queue_lag_required'):
                snapshot(metrics() + ''.join(altered), timing_required=True, revive_required=True)
        self.assertNotIn('revive_lag', snapshot(metrics(), timing_required=True))

    def test_candidate_wait_rejects_a_nonzero_revive_tail_when_timer_is_zero(self):
        prefix = ''.join(f'{REVIVE_LAG_NAME}{{queue_id="{queue}"}} 0\n' for queue in range(7))
        value = snapshot(metrics() + prefix + f'{REVIVE_LAG_NAME}{{queue_id="7"}} 1\n',
                         timing_required=True, revive_required=True)
        proof, passed = {}, Mock()
        control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, passed, revive_required=True)
        with patch.object(control, 'read', return_value=value), \
                patch('readable_pop_controls.time.monotonic', side_effect=[0, 1, 90]), \
                patch('readable_pop_controls.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'native_pop_control_budget_exceeded'):
                control('baseline', 'sdk-go')
        failure = proof['go']['baseline_timeout']
        self.assertEqual(failure['budget_seconds'], 90)
        self.assertEqual(failure['last_sample']['revive_lag']['7'], 1)
        self.assertEqual(failure['last_sample']['timing'], 0)
        passed.assert_not_called()

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

    def test_baseline_timeout_retains_only_last_failed_snapshot(self):
        first = snapshot(metrics_with_revive_lag(timing='2'), timing_required=False, revive_required=True)
        last = snapshot(metrics_with_revive_lag('1'), timing_required=False, revive_required=True)
        proof, passed = {}, Mock()
        control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, passed, revive_required=True)
        with patch.object(control, 'read', side_effect=[first, last]), \
                patch('readable_pop_controls.time.monotonic', side_effect=[0, 1, 2, 90]), \
                patch('readable_pop_controls.time.time_ns', side_effect=[1_000_000, 2_000_000]), \
                patch('readable_pop_controls.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'native_pop_control_budget_exceeded'):
                control('baseline', 'sdk-go')
        self.assertEqual(proof, {'go': {'baseline_timeout': dict(
            budget_seconds=90, samples_read=2, last_sample_unix_ms=2, last_sample=last)}})
        passed.assert_not_called()

    def test_successful_wait_leaves_no_timeout_record(self):
        first = snapshot(metrics_with_revive_lag('1'), timing_required=False, revive_required=True)
        last = snapshot(metrics_with_revive_lag(), timing_required=False, revive_required=True)
        proof = {}
        control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, Mock(), revive_required=True)
        with patch.object(control, 'read', side_effect=[first, last]), \
                patch('readable_pop_controls.time.sleep'):
            control('baseline', 'sdk-go')
        self.assertEqual(proof, {'go': {'baseline': last}})

    def test_closed_confirmation_retains_reappearing_responsibility(self):
        settled = snapshot(metrics_with_revive_lag(), timing_required=True, revive_required=True)
        for field in ('offset', 'checkpoint', 'timing', 'lag'):
            with self.subTest(field=field):
                reappeared = snapshot(metrics_with_revive_lag(**{field: '1'}), timing_required=True, revive_required=True)
                proof = {'go': {'held': snapshot(metrics_with_revive_lag(timing='2'), timing_required=True, revive_required=True)}}
                passed = Mock()
                control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, passed, revive_required=True)
                control.observed_timer = True
                with patch.object(control, 'read', side_effect=[settled, reappeared]), patch('readable_pop_controls.time.sleep'):
                    with self.assertRaisesRegex(RuntimeError, 'pop_responsibility_reappeared_after_sdk_close'):
                        control('closed', 'sdk-go')
                self.assertEqual(proof['go']['closed'], settled)
                self.assertEqual(proof['go']['closed_confirmation'], reappeared)
                passed.assert_not_called()
