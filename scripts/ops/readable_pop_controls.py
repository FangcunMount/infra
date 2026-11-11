"""Owned CI control: held deliveries must expose future POP responsibility.

No production entrypoint, mutation, consumer ACK, factory patch or raw export.
The existing public SDK fixture owns and closes all actual clients and stores.
"""
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
import re
import struct
import subprocess
import time
import urllib.request
import zlib

SYSTEM_TOPIC = 'rmq_sys_REVIVE_LOG_FangcunMount'
BUFFER_NAMES = ('rocketmq_pop_offset_buffer_size', 'rocketmq_pop_checkpoint_buffer_size')
# The pinned 5.5.1 exporter adds the unit suffix, but this gauge counts messages.
REVIVE_LAG_NAME = 'rocketmq_pop_revive_lag_milliseconds'
REVIVE_QUEUE_IDS = {str(queue_id) for queue_id in range(8)}


POP_LOG = '/home/rocketmq/logs/rocketmqlogs/pop.log'
TOPIC_CATALOG = '/home/rocketmq/store/config/topics.json'
CONSUMER_OFFSETS = '/home/rocketmq/store/config/consumerOffset.json'
REVIVE_OFFSET_KEY = SYSTEM_TOPIC + '@CID_RMQ_SYS_REVIVE_GROUP'
POP_LOG_BYTES = 256 * 1024
REVIVE_LINE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) .*?reviveQueueId=(\d+),\s*'
    r'find (ck|ack|batch ack), offset:(\d+), raw : (\{.*\})\s*$')
# The pinned Broker's pop.log encoder writes whole seconds in GMT+8.
POP_LOG_TIMEZONE = timezone(timedelta(hours=8))



def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def samples(raw, name):
    result = []
    for line in raw.splitlines():
        if not (line.startswith(name + '{') or line.startswith(name + ' ')):
            continue
        match = re.fullmatch(re.escape(name) + r'(?:\{(.*)\})? ([^ ]+)(?: [0-9]+)?', line)
        require(match is not None, 'invalid_native_pop_metric')
        labels, encoded, position = {}, match[1] or '', 0
        while position < len(encoded):
            pair = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\["\\n])*)"(?:,|$)', encoded[position:])
            require(pair is not None and pair[1] not in labels, 'invalid_native_pop_labels')
            labels[pair[1]] = json.loads('"' + pair[2] + '"')
            position += pair.end()
        require(len(match[2]) <= 32 and re.fullmatch(r'[+]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', match[2]),
                'invalid_native_pop_count')
        count = Decimal(match[2])
        require(count.is_finite() and 0 <= count <= 9223372036854775807 and count == count.to_integral_value(), 'invalid_native_pop_count')
        result.append((labels, int(count)))
    return result


def snapshot(raw, *, timing_required):
    require(isinstance(raw, str) and 0 < len(raw.encode()) <= 8 * 1024 * 1024, 'bounded_native_pop_metrics_required')
    counts = []
    for name in BUFFER_NAMES:
        values = samples(raw, name)
        require(len(values) == 1, 'complete_unique_pop_buffer_metrics_required')
        counts.append(values[0][1])
    timers = [count for labels, count in samples(raw, 'rocketmq_timing_messages') if labels.get('topic') == SYSTEM_TOPIC]
    require(len(timers) <= 1 and (not timing_required or len(timers) == 1), 'complete_unique_revive_timer_metric_required')
    lag_samples = samples(raw, REVIVE_LAG_NAME)
    revive_lag = {labels.get('queue_id'): count for labels, count in lag_samples}
    require(len(lag_samples) == len(REVIVE_QUEUE_IDS) and revive_lag.keys() == REVIVE_QUEUE_IDS,
            'complete_unique_revive_queue_lag_required')
    return dict(offset_buffer=counts[0], checkpoint_buffer=counts[1],
                timing=timers[0] if timers else None, timer_series_present=bool(timers),
                revive_lag=revive_lag,
                raw_sha256=hashlib.sha256(raw.encode()).hexdigest())


def zero(value, *, timing_required):
    # Missing timer series is allowed ONLY before any timing record exists in
    # the controlled new CI project. A positive future CK must then materialize
    # that series, and the settled control requires its explicit zero.
    # The timer decrements before the record is processed by the revive queue.
    return (value['offset_buffer'] == value['checkpoint_buffer'] == 0
            and not any(value['revive_lag'].values())
            and (value['timing'] == 0 or (not timing_required and value['timing'] is None)))


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_revive_field')
        result[key] = value
    return result


def revive_record(body, kind, queue, offset, routes):
    require(len(body) <= 16384, 'bounded_revive_metadata_required')
    data = json.loads(body, object_pairs_hook=unique_fields)
    require(isinstance(data, dict), 'invalid_revive_metadata')
    if (data.get('t'), data.get('c')) not in routes:
        return None
    q, start, pop = (data[k] for k in ('q', 'so', 'pt'))
    require(all(type(value) is int and value >= 0 for value in (q, start, pop)), 'invalid_revive_location')
    broker = data.get('bn')
    require(isinstance(broker, str) and 0 < len(broker) <= 128, 'invalid_revive_broker')
    require(0 <= queue < 8 and 0 <= offset < 2**63, 'invalid_revive_offset')
    key = json.dumps([queue, data['t'], data['c'], q, start, pop, broker], separators=(',', ':'))
    if kind == 'ck':
        count = data['n']
        require(type(count) is int and 0 <= count <= 127, 'invalid_ck_count')
        differences = data.get('d')
        if differences is None or differences == []:
            differences = range(count)
        require(isinstance(differences, (list, range)) and len(differences) == count
                and all(type(value) is int and value >= 0 for value in differences), 'invalid_ck_offsets')
        offsets = [start + value for value in differences]
    elif kind == 'ack':
        offsets = [data['ao']]
    else:
        offsets = data['aol']
    require(isinstance(offsets, list) and len(offsets) <= 127 and (offsets or kind == 'ck')
            and all(type(value) is int and start <= value < 2**63 for value in offsets)
            and len(set(offsets)) == len(offsets), 'invalid_revive_message_offsets')
    return dict(kind=kind, revive_queue=queue, revive_offset=offset, messages=len(offsets),
                route_sha256=hashlib.sha256(json.dumps([data['t'], data['c']], separators=(',', ':')).encode()).hexdigest(),
                merge_key_sha256=hashlib.sha256(key.encode()).hexdigest(),
                metadata_sha256=hashlib.sha256(body).hexdigest(),
                offset_sha256s=[hashlib.sha256(f'{key}:{value}'.encode()).hexdigest() for value in sorted(offsets)])


def revive_log_records(raw, routes):
    """Keep only fixed 5.5.1 records for the disposable subscriber routes."""
    require(len(raw.encode()) <= POP_LOG_BYTES, 'bounded_revive_log_required')
    records = {}
    malformed = 0
    for line in raw.splitlines():
        match = REVIVE_LINE.fullmatch(line)
        if not match:
            if re.search(r'reviveQueueId=.*find (?:ck|ack|batch ack), offset:', line):
                malformed += 1
            continue
        clock, queue, kind, offset, body = match.groups()
        try:
            scanned = datetime.strptime(clock, '%Y-%m-%d %H:%M:%S').replace(tzinfo=POP_LOG_TIMEZONE)
            scanned_ms = int(scanned.timestamp() * 1000)
            item = revive_record(body.encode(), kind, int(queue), int(offset), routes)
        except (RuntimeError, KeyError, ValueError, TypeError, RecursionError):
            malformed += 1
            continue
        if item is None:
            continue
        identity = (item['revive_queue'], item['revive_offset'], item['metadata_sha256'])
        record = records.setdefault(identity, dict(item, first_scan_unix_ms=scanned_ms, last_scan_unix_ms=scanned_ms))
        record['first_scan_unix_ms'] = min(record['first_scan_unix_ms'], scanned_ms)
        record['last_scan_unix_ms'] = max(record['last_scan_unix_ms'], scanned_ms)
    ordered = sorted(records.values(), key=lambda row: (row['revive_queue'], row['revive_offset'], row['metadata_sha256']))
    return dict(records=ordered[-64:], omitted_records=max(0, len(ordered)-64),
                malformed_records=malformed, retained_bytes=len(raw.encode()), drain_proven=False)


def retry_catalog(raw, routes):
    require(len(raw.encode()) <= POP_LOG_BYTES, 'bounded_retry_catalog_required')
    document = json.loads(raw, object_pairs_hook=unique_fields)
    require(isinstance(document, dict) and isinstance(document.get('dataVersion'), dict)
            and isinstance(document.get('topicConfigTable'), dict), 'invalid_retry_catalog')
    topics = set(document['topicConfigTable'])
    require({topic for topic, _ in routes} <= topics and SYSTEM_TOPIC in topics, 'incomplete_retry_catalog')
    expected = {f'%RETRY%{group}{separator}{topic}' for topic, group in routes for separator in ('_', '+')}
    expected.update(prefix+group for _, group in routes for prefix in ('%RETRY%', '%DLQ%'))
    return dict(source='broker_persisted_topic_config', observed_unix_ms=time.time_ns() // 1000000, checked=len(expected),
                present_sha256s=sorted(hashlib.sha256(topic.encode()).hexdigest() for topic in expected & topics),
                catalog_sha256=hashlib.sha256(raw.encode()).hexdigest())


def persisted_revive_offsets(raw):
    require(len(raw.encode()) <= POP_LOG_BYTES, 'bounded_revive_offsets_required')
    # Fastjson emits bare integer keys for queue IDs in the persisted map.
    normalized = re.sub(r'(?m)^(\s*)([0-7])(\s*:)', r'\1"\2"\3', raw)
    document = json.loads(normalized, object_pairs_hook=unique_fields)
    offsets = document['offsetTable'].get(REVIVE_OFFSET_KEY, {})
    require(isinstance(offsets, dict) and offsets.keys() <= REVIVE_QUEUE_IDS
            and all(type(value) is int and 0 <= value < 2**63 for value in offsets.values()),
            'invalid_revive_offsets')
    return dict(source='broker_persisted_consumer_offsets', committed=offsets,
                observed_unix_ms=time.time_ns() // 1_000_000, raw_sha256=hashlib.sha256(raw.encode()).hexdigest())


def revive_queue_bounds(raw):
    require(len(raw.encode()) <= POP_LOG_BYTES, 'bounded_revive_queue_bounds_required')
    result = {}
    for line in raw.splitlines():
        if not line.startswith('serverd-rocketmq'):
            continue
        match = re.fullmatch(r'serverd-rocketmq\s+([0-7])\s+([0-9]+)\s+([0-9]+)(?:\s+.*)?', line)
        require(match is not None and match[1] not in result, 'invalid_revive_queue_bounds')
        minimum, exclusive_maximum = int(match[2]), int(match[3])
        require(0 <= minimum <= exclusive_maximum < 2**63, 'invalid_revive_queue_bounds')
        result[match[1]] = dict(minimum=minimum, exclusive_maximum=exclusive_maximum)
    require(result.keys() == REVIVE_QUEUE_IDS, 'complete_revive_queue_bounds_required')
    return dict(source='broker_topic_status', queues=result,
                observed_unix_ms=time.time_ns() // 1_000_000, raw_sha256=hashlib.sha256(raw.encode()).hexdigest())


def decode_physical_revive(raw, queue, logical, physical, routes):
    # Pinned 5.5.1 MessageDecoder: only uncompressed IPv4 v1/v2 records.
    require(90 <= len(raw) <= 32768, 'bounded_physical_revive_record_required')
    size, magic, crc, recorded_queue, _, recorded_logical, recorded_physical, sysflag = struct.unpack_from(
        '>iiiiiqqi', raw)
    require(size == len(raw) and (recorded_queue, recorded_logical, recorded_physical) == (queue, logical, physical)
            and not sysflag & 0x31, 'physical_revive_record_identity_mismatch')
    topic_length_bytes = {-626843481: 1, -626843477: 2}.get(magic)
    require(topic_length_bytes is not None, 'physical_revive_magic_unavailable')
    body_length, = struct.unpack_from('>i', raw, 84)
    body_end = 88 + body_length
    require(0 < body_length <= 16384 and body_end + topic_length_bytes + 2 <= size,
            'physical_revive_body_bounds')
    body = raw[88:body_end]
    # RocketMQ UtilAll.crc32 persists the low 31 bits.
    require((zlib.crc32(body) & 0x7fffffff) == crc, 'physical_revive_body_crc_mismatch')
    topic_start = body_end + topic_length_bytes
    topic_length = int.from_bytes(raw[body_end:topic_start], 'big')
    topic_end = topic_start + topic_length
    require(topic_end + 2 <= size and raw[topic_start:topic_end] == SYSTEM_TOPIC.encode(),
            'physical_revive_topic_mismatch')
    properties_length, = struct.unpack_from('>H', raw, topic_end)
    require(topic_end + 2 + properties_length == size, 'physical_revive_properties_bounds')
    tags = [part[5:] for part in raw[topic_end+2:].split(b'\x02') if part.startswith(b'TAGS\x01')]
    require(len(tags) == 1, 'physical_revive_tag_required')
    kind = {b'ck': 'ck', b'ack': 'ack', b'bAck': 'batch ack'}.get(tags[0])
    require(kind is not None, 'physical_revive_tag_unknown')
    result = revive_record(body, kind, queue, logical, routes)
    require(result is not None, 'physical_revive_route_unavailable')
    return dict(result, physical_record_sha256=hashlib.sha256(raw).hexdigest())


def physical_revive_records(read, committed, bounds, lag):
    """Read only the first mapped files of this small disposable Broker."""
    first_file = '00000000000000000000'
    store = '/home/rocketmq/store'
    deadline = time.monotonic() + 35
    records, queues = [], {}
    for key, count in sorted(lag.items()):
        if count <= 0:
            continue
        queue = int(key)
        try:
            cursor = committed[key]
            minimum, maximum = bounds[key]['minimum'], bounds[key]['exclusive_maximum']
            require(0 <= minimum <= cursor < maximum <= 512 and maximum - cursor - 1 == count <= 8,
                    'physical_revive_range_not_verified')
            start = max(minimum, cursor - 8)
            path = f'{store}/consumequeue/{SYSTEM_TOPIC}/{queue}/{first_file}'
            index_size = (maximum - start) * 20
            cq = read(path, start * 20, index_size, deadline)
            require(len(cq) == index_size, 'physical_revive_index_incomplete')
            selected = []
            for offset, (physical, size, _) in enumerate(struct.iter_unpack('>qiq', cq), start):
                require(0 <= physical < 134217728 and 90 <= size <= 32768 and physical+size <= 134217728,
                        'physical_revive_index_outside_first_file')
                raw = read(f'{store}/commitlog/{first_file}', physical, size, deadline)
                selected.append((raw, queue, offset, physical))
            require(read(path, start * 20, len(cq), deadline) == cq, 'physical_revive_index_changed')
            records.extend(selected)
            queues[key] = dict(start=start, exclusive_maximum=maximum, index_sha256=hashlib.sha256(cq).hexdigest())
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, struct.error, subprocess.SubprocessError):
            queues[key] = dict(error='physical_revive_queue_unavailable')
    return records, queues


class OwnedPopControls:
    def __init__(self, run, admin, broker, project, manifest, proof, passed, *, trace_rebound=False):
        self.run, self.admin, self.broker, self.project = run, admin, broker, project
        self.manifest, self.proof, self.passed = manifest, proof, passed
        self.trace_rebound = trace_rebound
        self.url = None
        self.observed_timer = False
        self.trace_container = None
        self.trace_configuration = None

    def trace_identity(self, value):
        labels = value['Config']['Labels']
        state = value['State']
        require(labels.get('com.docker.compose.project') == self.project
                and labels.get('com.docker.compose.service') == 'broker'
                and state['Running'] is True and state['StartedAt'],
                'owned_pop_trace_identity_required')
        require(re.fullmatch('[0-9a-f]{64}', value['Id'])
                and re.fullmatch('sha256:[0-9a-f]{64}', value['Image']),
                'immutable_pop_trace_identity_required')
        return dict(container_id=value['Id'], image_id=value['Image'], started_at=state['StartedAt'])

    def configure(self):
        from final_image_candidate import ci_guard
        ci_guard(os.environ)
        require(re.fullmatch('rocketmq-m2-[0-9a-f]{12}', self.project), 'owned_pop_project_required')
        value = json.loads(self.run(['docker', 'inspect', self.broker]).stdout)[0]
        require(value['Config']['Labels'].get('com.docker.compose.project') == self.project,
                'owned_pop_container_required')
        bindings = value['HostConfig']['PortBindings']['5557/tcp']
        require(len(bindings) == 1 and bindings[0]['HostIp'] == '127.0.0.1'
                and re.fullmatch('[0-9]{1,5}', bindings[0]['HostPort']), 'owned_loopback_pop_scrape_required')
        properties = {}
        for line in self.admin('getBrokerConfig').splitlines():
            pair = line.split('=', 1)
            if len(pair) == 2:
                properties[pair[0].strip()] = pair[1].strip()
        require(properties.get('brokerClusterName') == 'FangcunMount'
                and properties.get('timerWheelEnable') == properties.get('enablePopMetrics') == 'true',
                'pinned_native_pop_metrics_required')
        if self.trace_rebound:
            require(properties.get('enablePopLog') == 'true', 'owned_pop_trace_config_required')
            self.trace_container = self.trace_identity(value)
            self.trace_configuration = {
                key: properties[key] for key in ('enableSkipLongAwaitingAck', 'reviveAckWaitMs', 'enablePopLog')
            }
        self.url = 'http://127.0.0.1:' + bindings[0]['HostPort'] + '/metrics'

    def read(self, required):
        if self.url is None:
            self.configure()
        with urllib.request.urlopen(self.url, timeout=3) as response:
            require(response.status == 200, 'native_pop_scrape_failed')
            raw = response.read(8 * 1024 * 1024 + 1)
        return snapshot(raw.decode(), timing_required=required)

    def trace(self, sample):
        require(self.url is not None and self.trace_container is not None, 'owned_pop_trace_required')
        routes = {(row['physical_topic'], row['consumer_group']) for row in self.manifest['routes']
                  if row.get('physical_topic') and row.get('consumer_group')}
        require(bool(routes), 'known_trace_routes_required')
        container = self.trace_container['container_id']

        def verify_identity():
            live, = json.loads(self.run(['docker', 'inspect', container], timeout=5).stdout)
            require(self.trace_identity(live) == self.trace_container, 'owned_pop_trace_identity_drift')

        verify_identity()

        def capture(args, parse):
            try:
                result = self.run(['docker', 'exec', container, *args], timeout=10, required=False)
                require(result.returncode == 0, 'owned_pop_trace_read_failed')
                return parse(result.stdout)
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
                return dict(error='owned_pop_trace_read_unavailable')

        def persisted_offsets():
            return capture(['head', '-c', str(POP_LOG_BYTES + 1), CONSUMER_OFFSETS], persisted_revive_offsets)

        before = persisted_offsets()
        records = capture(['tail', '-c', str(POP_LOG_BYTES), POP_LOG], lambda raw: revive_log_records(raw, routes))
        bounds = capture(['java', '-Xms32m', '-Xmx128m', '-cp', '/opt/rocketmq/conf:/opt/rocketmq/lib/*',
                          'org.apache.rocketmq.tools.command.MQAdminStartup', 'topicStatus',
                          '-n', 'nameserver:9876', '-t', SYSTEM_TOPIC], revive_queue_bounds)
        retries = capture(['head', '-c', str(POP_LOG_BYTES + 1), TOPIC_CATALOG], lambda raw: retry_catalog(raw, routes))

        def read_bytes(path, offset, count, deadline):
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'physical_revive_trace_budget_exceeded')
            result = self.run(['docker', 'exec', container, 'sh', '-c',
                'dd if="$1" bs=1 skip="$2" count="$3" status=none | base64', 'physical-revive',
                path, str(offset), str(count)], timeout=min(remaining, 3), required=False)
            require(result.returncode == 0 and len(result.stdout) <= count * 2 + 8,
                    'physical_revive_read_unavailable')
            raw = base64.b64decode(''.join(result.stdout.split()), validate=True)
            require(len(raw) == count, 'physical_revive_read_incomplete')
            return raw

        selected, queues = physical_revive_records(read_bytes, before.get('committed', {}),
                                                    bounds.get('queues', {}), sample.get('revive_lag', {}))
        physical = []
        unreadable = []
        for raw, queue, logical, offset in selected:
            try:
                physical.append(decode_physical_revive(raw, queue, logical, offset, routes))
            except (RuntimeError, KeyError, ValueError, TypeError, RecursionError, struct.error):
                unreadable.append(dict(queue=queue, offset=logical))
        after = persisted_offsets()
        verify_identity()
        return dict(offsets_before=before, offsets_after=after, records=records,
                    broker_identity=self.trace_container, broker_configuration=self.trace_configuration,
                    queue_bounds=bounds, retry_catalog=retries,
                    physical_storage=dict(records=physical, queues=queues, unreadable=unreadable, drain_proven=False),
                    drain_proven=False)

    def retain_trace(self, record):
        if self.trace_rebound:
            try:
                record['trace'] = self.trace(record.get('last_sample') or record.get('closed_confirmation') or {})
            except (RuntimeError, OSError, ValueError, TypeError, KeyError):
                record['trace'] = dict(error='owned_pop_trace_unavailable', drain_proven=False)

    def wait(self, predicate, *, required, budget, record, stage):
        deadline = time.monotonic() + budget
        samples_read = 0
        last_sample = None
        last_sample_unix_ms = None
        while time.monotonic() < deadline:
            value = self.read(required)
            if predicate(value):
                return value
            samples_read += 1
            last_sample = value
            last_sample_unix_ms = time.time_ns() // 1_000_000
            time.sleep(.2)
        timeout = dict(budget_seconds=budget, samples_read=samples_read,
                       last_sample_unix_ms=last_sample_unix_ms, last_sample=last_sample)
        record[stage + '_timeout'] = timeout
        self.retain_trace(timeout)
        raise RuntimeError('native_pop_control_budget_exceeded')

    def __call__(self, stage, language):
        require(language in ('sdk-go', 'sdk-python') and stage in ('baseline', 'subscribed', 'held', 'closed'), 'fixed_pop_control_stage_required')
        suffix = 'go' if language == 'sdk-go' else 'python'
        record = self.proof.setdefault(suffix, {})
        require(stage not in record, 'duplicate_pop_control_stage')
        if stage == 'baseline':
            record[stage] = self.wait(lambda v: zero(v, timing_required=self.observed_timer),
                                      required=self.observed_timer, budget=90, record=record, stage=stage)
        elif stage == 'subscribed':
            require('baseline' in record, 'pop_baseline_required')
            routes = [row for row in self.manifest['routes'] if row['subscription'] == 'sdk-shared-' + suffix]
            groups = {row['consumer_group'] for row in routes}
            require(len(groups) == 1, 'one_actual_shared_pop_group_required')
            raw = self.admin('consumerConnection', '-g', next(iter(groups)))
            require(re.search(r'^ConsumeType: CONSUME_ACTIVELY$', raw, re.MULTILINE), 'actual_grpc_simple_consumer_required')
            record[stage] = dict(consume_type='CONSUME_ACTIVELY', connection_sha256=hashlib.sha256(raw.encode()).hexdigest())
        elif stage == 'held':
            require('subscribed' in record, 'registered_pop_subscriber_required')
            record[stage] = self.wait(lambda v: v['timing'] is not None and v['timing'] > 0,
                                      required=False, budget=25, record=record, stage=stage)
            self.observed_timer = True
            self.passed('readable_pop_' + suffix + '_held_future_checkpoint_blocks_drain')
        else:
            require('held' in record and self.observed_timer, 'positive_future_checkpoint_control_required')
            record[stage] = self.wait(lambda v: zero(v, timing_required=True), required=True, budget=90, record=record, stage=stage)
            time.sleep(1)
            record['closed_confirmation'] = self.read(True)
            settled = zero(record['closed_confirmation'], timing_required=True)
            if not settled:
                self.retain_trace(record)
            require(settled, 'pop_responsibility_reappeared_after_sdk_close')
            self.passed('readable_pop_' + suffix + '_acked_and_closed_responsibility_zero')
