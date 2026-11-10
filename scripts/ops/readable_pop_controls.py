"""Owned CI control: held deliveries must expose future POP responsibility.

No production entrypoint, mutation, consumer ACK, factory patch or raw export.
The existing public SDK fixture owns and closes all actual clients and stores.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
import re
import time
import urllib.request

SYSTEM_TOPIC = 'rmq_sys_REVIVE_LOG_FangcunMount'
BUFFER_NAMES = ('rocketmq_pop_offset_buffer_size', 'rocketmq_pop_checkpoint_buffer_size')
POP_LOG = '/home/rocketmq/logs/rocketmqlogs/pop.log'
TOPIC_CATALOG = '/home/rocketmq/store/config/topics.json'
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
    return dict(offset_buffer=counts[0], checkpoint_buffer=counts[1],
                timing=timers[0] if timers else None, timer_series_present=bool(timers),
                raw_sha256=hashlib.sha256(raw.encode()).hexdigest())


def zero(value, *, timing_required):
    # Missing timer series is allowed ONLY before any timing record exists in
    # the controlled new CI project. A positive future CK must then materialize
    # that series, and the settled control requires its explicit zero.
    return (value['offset_buffer'] == value['checkpoint_buffer'] == 0
            and (value['timing'] == 0 or (not timing_required and value['timing'] is None)))


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_revive_field')
        result[key] = value
    return result


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
            require(len(body) <= 16384, 'bounded_revive_metadata_required')
            scanned = datetime.strptime(clock, '%Y-%m-%d %H:%M:%S').replace(tzinfo=POP_LOG_TIMEZONE)
            scanned_ms = int(scanned.timestamp() * 1000)
            data = json.loads(body, object_pairs_hook=unique_fields)
            require(isinstance(data, dict), 'invalid_revive_metadata')
            if (data.get('t'), data.get('c')) not in routes:
                continue
            q, start, pop = (data[k] for k in ('q', 'so', 'pt'))
            require(all(type(value) is int and value >= 0 for value in (q, start, pop)), 'invalid_revive_location')
            broker = data.get('bn')
            require(isinstance(broker, str) and 0 < len(broker) <= 128, 'invalid_revive_broker')
            queue, offset = int(queue), int(offset)
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
        except (RuntimeError, KeyError, ValueError, TypeError, RecursionError):
            malformed += 1
            continue
        digest = hashlib.sha256(body.encode()).hexdigest()
        record = records.setdefault((queue, offset, digest), dict(
            kind=kind, revive_queue=queue, revive_offset=offset, messages=len(offsets),
            merge_key_sha256=hashlib.sha256(key.encode()).hexdigest(), metadata_sha256=digest,
            first_scan_unix_ms=scanned_ms, last_scan_unix_ms=scanned_ms,
            offset_sha256s=[hashlib.sha256(f'{key}:{value}'.encode()).hexdigest() for value in sorted(offsets)]))
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


class OwnedPopControls:
    def __init__(self, run, admin, broker, project, manifest, proof, passed, *, trace_rebound=False):
        self.run, self.admin, self.broker, self.project = run, admin, broker, project
        self.manifest, self.proof, self.passed = manifest, proof, passed
        self.trace_rebound = trace_rebound
        self.url = None
        self.observed_timer = False

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
        self.url = 'http://127.0.0.1:' + bindings[0]['HostPort'] + '/metrics'

    def read(self, required):
        if self.url is None:
            self.configure()
        with urllib.request.urlopen(self.url, timeout=3) as response:
            require(response.status == 200, 'native_pop_scrape_failed')
            raw = response.read(8 * 1024 * 1024 + 1)
        return dict(observed_unix_ms=time.time_ns() // 1000000, **snapshot(raw.decode(), timing_required=required))

    def wait(self, predicate, *, required, budget):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            value = self.read(required)
            if predicate(value):
                return value
            time.sleep(.2)
        raise RuntimeError('native_pop_control_budget_exceeded')

    def retry_snapshot(self, routes):
        try:
            result = self.run(['docker', 'exec', self.broker, 'head', '-c', str(POP_LOG_BYTES + 1),
                               TOPIC_CATALOG], timeout=5, required=False)
            require(result.returncode == 0, 'retry_catalog_unavailable')
            return retry_catalog(result.stdout, routes)
        except (RuntimeError, OSError, ValueError):
            return dict(error='retry_catalog_unavailable')

    def trace(self, suffix):
        # Called only after a failed confirmation, after configure verified the fixture.
        require(self.url is not None, 'owned_pop_trace_required')
        routes = {(row['physical_topic'], row['consumer_group']) for row in self.manifest['routes']
                  if row['subscription'] == 'sdk-shared-' + suffix}
        require(bool(routes), 'known_trace_routes_required')
        retry_before = self.retry_snapshot(routes)
        observed = []
        for _ in range(6):
            time.sleep(4)
            try:
                observed.append(self.read(True))
            except (RuntimeError, OSError, ValueError):
                observed.append(dict(observed_unix_ms=time.time_ns() // 1000000, error='pop_sample_unavailable'))
        result = self.run(['docker', 'exec', self.broker, 'tail', '-c', str(POP_LOG_BYTES), POP_LOG],
                          timeout=5, required=False)
        evidence = dict(samples=observed, retry_before=retry_before, retry_after=self.retry_snapshot(routes))
        if result.returncode:
            return dict(**evidence, error='revive_log_unavailable', drain_proven=False)
        return dict(**evidence, **revive_log_records(result.stdout, routes))

    def __call__(self, stage, language):
        require(language in ('sdk-go', 'sdk-python') and stage in ('baseline', 'subscribed', 'held', 'closed'), 'fixed_pop_control_stage_required')
        suffix = 'go' if language == 'sdk-go' else 'python'
        record = self.proof.setdefault(suffix, {})
        require(stage not in record, 'duplicate_pop_control_stage')
        if stage == 'baseline':
            record[stage] = self.wait(lambda v: zero(v, timing_required=self.observed_timer),
                                      required=self.observed_timer, budget=90)
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
                                      required=False, budget=25)
            self.observed_timer = True
            self.passed('readable_pop_' + suffix + '_held_future_checkpoint_blocks_drain')
        else:
            require('held' in record and self.observed_timer, 'positive_future_checkpoint_control_required')
            record[stage] = self.wait(lambda v: zero(v, timing_required=True), required=True, budget=90)
            time.sleep(1)
            record['closed_confirmation'] = self.read(True)
            settled = zero(record['closed_confirmation'], timing_required=True)
            if not settled and self.trace_rebound:
                try:
                    record['rebound_trace'] = self.trace(suffix)
                except (RuntimeError, OSError, ValueError):
                    record['rebound_trace'] = dict(error='owned_pop_trace_unavailable', drain_proven=False)
            require(settled, 'pop_responsibility_reappeared_after_sdk_close')
            self.passed('readable_pop_' + suffix + '_acked_and_closed_responsibility_zero')
