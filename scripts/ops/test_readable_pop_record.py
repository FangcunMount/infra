import json
import struct
import unittest
import zlib

from readable_pop_record import TOPIC, inspect_record


def fixture(*, tag='ack', body=None, version=1, flags=0, topic=TOPIC):
    body = json.dumps(body if body is not None else dict(c='private-group', t='private-topic', ao=3)).encode()
    properties = ('TAGS\x01' + tag + '\x02').encode()
    raw = (struct.pack('>iIiiqqI', -626843481 if version == 1 else -626843477,
                       zlib.crc32(body), 0, 0, 7, 123, flags)
           + bytes(8 + (20 if flags & 16 else 8) + 8 + (20 if flags & 32 else 8) + 4 + 8)
           + struct.pack('>i', len(body)) + body
           + struct.pack('>B' if version == 1 else '>H', len(topic.encode())) + topic.encode()
           + struct.pack('>H', len(properties)) + properties)
    return struct.pack('>i', len(raw) + 4) + raw


class ReadablePopRecordTest(unittest.TestCase):
    def decode(self, raw):
        return inspect_record(raw, queue=0, queue_offset=7, physical_offset=123)

    def test_versions_ipv6_and_ack_kinds_export_hashes_without_private_metadata(self):
        for version in (1, 2):
            for flags in (0, 16, 32, 48):
                for tag in ('ack', 'bAck'):
                    result = self.decode(fixture(version=version, flags=flags, tag=tag))
                    self.assertEqual(result['kind'], tag)
                    self.assertFalse(result['drain_proven'])
                    self.assertNotIn('private', json.dumps(result))

    def test_actual_checkpoint_count_is_preserved_never_resolved_as_acked(self):
        for count in (0, 1, 16, 127):
            result = self.decode(fixture(tag='ck', body=dict(n=count, c='private-group', t='private-topic')))
            self.assertEqual(result['checkpoint_messages'], count)
            self.assertFalse(result['drain_proven'])
        for count in (True, -1, 128, None, '1'):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.decode(fixture(tag='ck', body=dict(n=count)))

    def test_missing_checkpoint_count_and_consistent_size_truncation_are_unknown(self):
        with self.assertRaises(ValueError):
            self.decode(fixture(tag='ck', body=dict(c='private-group')))
        raw = fixture()
        for size in range(91, len(raw)):
            short = struct.pack('>i', size) + raw[4:size]
            with self.subTest(size=size), self.assertRaises(ValueError):
                self.decode(short)

    def test_corruption_compression_other_topic_unknown_kind_and_location_are_refused(self):
        original = fixture()
        damaged = bytearray(original); damaged[8] ^= 1
        for raw in (b'', original[:-1], original + b'x', bytes(damaged),
                    fixture(flags=1), fixture(tag='unknown'), fixture(topic='business.topic')):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                self.decode(raw)
        for changes in (dict(queue=1), dict(queue_offset=8), dict(physical_offset=124), dict(queue=True)):
            arguments = dict(queue=0, queue_offset=7, physical_offset=123); arguments.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                inspect_record(original, **arguments)
