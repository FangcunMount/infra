import json
import struct
import unittest
import zlib
from unittest.mock import Mock, patch

from readable_pop_controls import (
    BUFFER_NAMES, REVIVE_LAG_NAME, REVIVE_OFFSET_KEY, SYSTEM_TOPIC, OwnedPopControls,
    decode_physical_revive, persisted_revive_offsets, physical_revive_records,
    revive_log_records, revive_queue_bounds, snapshot, zero,
)


def metrics(*, offset='0', checkpoint='0', timing='0', include_timer=True, lag='0'):
    raw = (BUFFER_NAMES[0] + '{cluster="FangcunMount",node_type="master"} ' + offset + '\n'
           + BUFFER_NAMES[1] + '{cluster="FangcunMount",node_type="master"} ' + checkpoint + '\n')
    if include_timer:
        raw += 'rocketmq_timing_messages{cluster="FangcunMount",topic="' + SYSTEM_TOPIC + '"} ' + timing + '\n'
    return raw + ''.join(f'{REVIVE_LAG_NAME}{{queue_id="{queue}"}} {lag if queue == 2 else "0"}\n'
                         for queue in range(8))


class ReadablePopControlsTest(unittest.TestCase):
    def test_future_checkpoint_prevents_zero_even_with_no_buffer_or_ordinary_inflight(self):
        raw = metrics(timing='2') + 'rocketmq_consumer_inflight_messages{consumer_group="fake"} 0\n'
        value = snapshot(raw, timing_required=True)
        self.assertFalse(zero(value, timing_required=True))
        for change in (dict(offset='1'), dict(checkpoint='1')):
            self.assertFalse(zero(snapshot(metrics(**change), timing_required=True), timing_required=True))
        self.assertTrue(zero(snapshot(metrics(), timing_required=True), timing_required=True))

    def test_timer_to_revive_handoff_blocks_zero_after_timer_decrements(self):
        value = snapshot(metrics(lag='2'), timing_required=True)
        self.assertEqual(value['timing'], 0)
        self.assertEqual(value['offset_buffer'], 0)
        self.assertEqual(value['checkpoint_buffer'], 0)
        self.assertEqual(value['revive_lag']['2'], 2)
        self.assertFalse(zero(value, timing_required=True))
        self.assertFalse(zero(snapshot(metrics(include_timer=False, lag='2'), timing_required=False),
                              timing_required=False))

    def test_revive_queue_lag_requires_exact_complete_unique_series(self):
        queue_seven = f'{REVIVE_LAG_NAME}{{queue_id="7"}} 0\n'
        raw = metrics()
        for change in ('', queue_seven.replace('"7"', '"6"'), queue_seven.replace('"7"', '"8"'),
                       queue_seven.replace('queue_id', 'unknown')):
            with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, 'complete_unique_revive_queue_lag_required'):
                snapshot(raw.replace(queue_seven, change), timing_required=True)
        for count in ('NaN', '0.5', '-1'):
            with self.subTest(count=count), self.assertRaisesRegex(RuntimeError, 'invalid_native_pop_count'):
                snapshot(metrics(lag=count), timing_required=True)

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
        first = snapshot(metrics(timing='2'), timing_required=False)
        last = snapshot(metrics(lag='1'), timing_required=False)
        proof, passed = {}, Mock()
        control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, passed)
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
        first = snapshot(metrics(lag='1'), timing_required=False)
        last = snapshot(metrics(), timing_required=False)
        proof = {}
        control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, Mock())
        with patch.object(control, 'read', side_effect=[first, last]), \
                patch('readable_pop_controls.time.sleep'):
            control('baseline', 'sdk-go')
        self.assertEqual(proof, {'go': {'baseline': last}})

    def test_trace_binds_committed_offsets_and_exact_queue_bounds(self):
        raw = '{"offsetTable":{"' + REVIVE_OFFSET_KEY + '":{\n2:0\n}}}'
        self.assertEqual(persisted_revive_offsets(raw)['committed'], {'2': 0})
        with self.assertRaisesRegex(RuntimeError, 'duplicate_revive_field'):
            persisted_revive_offsets(raw.replace('2:0', '2:0,"2":1'))
        bounds = '\n'.join(f'serverd-rocketmq {q} 0 {2 if q == 2 else 0}' for q in range(8))
        self.assertEqual(revive_queue_bounds(bounds)['queues']['2'], {'minimum': 0, 'exclusive_maximum': 2})
        with self.assertRaisesRegex(RuntimeError, 'complete_revive_queue_bounds_required'):
            revive_queue_bounds(bounds.rsplit('\n', 1)[0])

    def test_trace_keeps_hashes_and_matches_ck_ack_by_original_identity(self):
        core = '"t":"fixture-topic","c":"fixture-group","q":0,"so":1,"pt":2,"bn":"broker"'
        raw = ('2026-11-10 12:00:00 INFO reviveQueueId=2, find ck, offset:0, raw : {' + core + ',"n":1,"d":[0]}\n'
               '2026-11-10 12:00:01 INFO reviveQueueId=2, find ack, offset:1, raw : {' + core + ',"ao":1}\n')
        rows = revive_log_records(raw, {('fixture-topic', 'fixture-group')})['records']
        self.assertEqual([row['revive_offset'] for row in rows], [0, 1])
        self.assertEqual(rows[0]['merge_key_sha256'], rows[1]['merge_key_sha256'])
        self.assertEqual(rows[0]['offset_sha256s'], rows[1]['offset_sha256s'])
        self.assertNotIn('fixture-topic', repr(rows))

    def test_physical_revive_matches_ck_ack_and_batch_ack(self):
        routes = {('fixture-topic', 'fixture-group')}
        core = dict(t='fixture-topic', c='fixture-group', q=0, so=1, pt=2, bn='broker-a')
        topic = SYSTEM_TOPIC.encode()
        rows = []
        for offset, (tag, fields, topic_width) in enumerate([
                (b'ck', dict(n=1, d=[0]), 1), (b'ack', dict(ao=1), 1), (b'bAck', dict(aol=[1]), 2)]):
            body = json.dumps(dict(core, **fields)).encode()
            properties = b'TAGS\x01' + tag + b'\x02'
            tail = (b'\x00' * 44 + struct.pack('>i', len(body)) + body
                    + len(topic).to_bytes(topic_width, 'big') + topic
                    + struct.pack('>H', len(properties)) + properties)
            magic = -626843481 if topic_width == 1 else -626843477
            crc = zlib.crc32(body) & 0x7fffffff
            raw = struct.pack('>iiiiiqqi', 40 + len(tail), magic, crc, 2, 0, offset, 100, 0) + tail
            rows.append(decode_physical_revive(raw, 2, offset, 100, routes))
        self.assertEqual([row['kind'] for row in rows], ['ck', 'ack', 'batch ack'])
        self.assertEqual(len({row['merge_key_sha256'] for row in rows}), 1)
        self.assertEqual(len({tuple(row['offset_sha256s']) for row in rows}), 1)
        self.assertNotIn('fixture-topic', repr(rows))
        self.assertGreaterEqual(zlib.crc32(body), 0x80000000)
        with self.assertRaisesRegex(RuntimeError, 'physical_revive_record_identity_mismatch'):
            decode_physical_revive(raw, 2, 1, 100, routes)
        with self.assertRaisesRegex(RuntimeError, 'physical_revive_body_crc_mismatch'):
            decode_physical_revive(raw[:88] + b'x' + raw[89:], 2, 2, 100, routes)
        with self.assertRaisesRegex(RuntimeError, 'physical_revive_topic_mismatch'):
            decode_physical_revive(raw.replace(topic, b'x' * len(topic)), 2, 2, 100, routes)

    def test_physical_revive_bounds_reject_truncated_and_changing_indexes(self):
        index = struct.pack('>qiq', 10, 90, 0) + struct.pack('>qiq', 100, 90, 0)
        bounds = {'2': dict(minimum=0, exclusive_maximum=2)}
        raw = b'x' * 90
        read = Mock(side_effect=[index, raw, raw, index])
        selected, queues = physical_revive_records(read, {'2': 0}, bounds, {'2': 1})
        self.assertEqual(selected, [(raw, 2, 0, 10), (raw, 2, 1, 100)])
        self.assertEqual(queues['2']['exclusive_maximum'], 2)
        for samples in ([index[:20]], [index, raw, raw, index[::-1]]):
            selected, queues = physical_revive_records(Mock(side_effect=samples), {'2': 0}, bounds, {'2': 1})
            self.assertEqual(selected, [])
            self.assertIn('error', queues['2'])
        read = Mock()
        selected, queues = physical_revive_records(read, {'2': 0}, bounds, {'2': 2})
        self.assertEqual(selected, [])
        self.assertIn('error', queues['2'])
        read.assert_not_called()

    def test_trace_refuses_restarted_container_before_any_storage_read(self):
        broker = {
            'Id': 'a' * 64,
            'Image': 'sha256:' + 'b' * 64,
            'Config': {'Labels': {'com.docker.compose.project': 'owned',
                                  'com.docker.compose.service': 'broker'}},
            'State': {'Running': True, 'StartedAt': 'before'},
        }
        run = Mock()
        control = OwnedPopControls(run, Mock(), 'fixture-broker', 'owned',
                                   {'routes': [{'physical_topic': 'topic', 'consumer_group': 'group'}]},
                                   {}, Mock(), trace_rebound=True)
        control.url = 'http://127.0.0.1:5557/metrics'
        control.trace_container = control.trace_identity(broker)
        broker['State']['StartedAt'] = 'after'
        run.return_value.stdout = json.dumps([broker])
        with self.assertRaisesRegex(RuntimeError, 'owned_pop_trace_identity_drift'):
            control.trace({})
        run.assert_called_once_with(['docker', 'inspect', broker['Id']], timeout=5)

    def test_timeout_trace_cannot_approve_drain(self):
        proof, passed = {}, Mock()
        control = OwnedPopControls(Mock(), Mock(), 'unused', 'unused', {}, proof, passed, trace_rebound=True)
        value = snapshot(metrics(lag='1'), timing_required=False)
        with patch.object(control, 'read', return_value=value), \
                patch.object(control, 'trace', side_effect=RuntimeError('read unavailable')), \
                patch('readable_pop_controls.time.monotonic', side_effect=[0, 1, 90]), \
                patch('readable_pop_controls.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'native_pop_control_budget_exceeded'):
                control('baseline', 'sdk-go')
        timeout = proof['go']['baseline_timeout']
        self.assertEqual(timeout['last_sample'], value)
        self.assertFalse(timeout['trace']['drain_proven'])
        passed.assert_not_called()

    def test_closed_confirmation_retains_reappearing_responsibility(self):
        settled = snapshot(metrics(), timing_required=True)
        for field in ('offset', 'checkpoint', 'timing', 'lag'):
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
