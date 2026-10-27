"""Read-only decoder for fixed 5.5.1 revive records, never business messages.

This is metadata inspection, not a drain/ACK/recovery decision. No I/O occurs.
Layout: pinned MessageDecoder / MessageSysFlag; metadata: PopCheckPoint / AckMsg.
"""
import hashlib
import json
import struct
import zlib

TOPIC = 'rmq_sys_REVIVE_LOG_FangcunMount'
MAGIC = {-626843481: 1, -626843477: 2}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate_system_metadata_field')
        value[key] = item
    return value


def inspect_record(raw, *, queue, queue_offset, physical_offset):
    require(isinstance(raw, bytes) and 91 <= len(raw) <= 65536, 'bounded_system_record_required')
    require(all(type(n) is int and n >= 0 for n in (queue, queue_offset, physical_offset)) and queue < 8,
            'exact_frozen_revive_location_required')
    position = 0

    def take(size):
        nonlocal position
        require(size >= 0 and position + size <= len(raw), 'truncated_system_record')
        result = raw[position:position + size]
        position += size
        return result

    def number(fmt):
        return struct.unpack('>' + fmt, take(struct.calcsize('>' + fmt)))[0]

    require(number('i') == len(raw), 'system_record_size_differs')
    version = MAGIC.get(number('i'))
    require(version is not None, 'unsupported_system_record_version')
    crc = number('I')
    require(number('i') == queue, 'system_queue_differs')
    take(4)  # Flag.
    require(number('q') == queue_offset and number('q') == physical_offset, 'system_offset_differs')
    flags = number('I')
    require(flags & 1 == 0, 'compressed_system_record_requires_separate_audit')
    take(8 + (20 if flags & 16 else 8) + 8 + (20 if flags & 32 else 8) + 4 + 8)
    size = number('i')
    require(0 < size <= 16384, 'bounded_system_metadata_required')
    body = take(size)
    # RocketMQ 5.5.1 UtilAll.crc32 masks the high bit (not unsigned CRC32).
    require(zlib.crc32(body) & 0x7fffffff == crc, 'system_metadata_crc_differs')
    topic = take(number('B' if version == 1 else 'H'))
    require(topic == TOPIC.encode(), 'business_record_refused')
    properties = take(number('H')).decode('utf-8')
    require(position == len(raw), 'system_record_trailing_bytes')
    pairs = [part.split('\x01') for part in properties.split('\x02') if part]
    require(all(len(pair) == 2 for pair in pairs), 'invalid_system_properties')
    properties = unique(pairs)
    tag = properties.get('TAGS')
    require(tag in ('ck', 'ack', 'bAck'), 'unknown_revive_record_kind')
    document = json.loads(body, object_pairs_hook=unique)
    require(isinstance(document, dict), 'system_metadata_object_required')
    count = document.get('n') if tag == 'ck' else None
    if tag == 'ck':
        require(type(count) is int and 0 <= count <= 127, 'invalid_checkpoint_message_count')
    # Deliberately no raw body, message ID, tenant, group, reference or wire.
    return dict(schema='readable-pop-system-record/v1', kind=tag,
                checkpoint_messages=count, record_sha256=hashlib.sha256(raw).hexdigest(),
                metadata_sha256=hashlib.sha256(body).hexdigest(), metadata_field_count=len(document),
                queue=queue, queue_offset=queue_offset, physical_offset=physical_offset,
                read_only=True, drain_proven=False)
