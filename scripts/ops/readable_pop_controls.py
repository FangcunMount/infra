"""Owned CI control: held deliveries must expose future POP responsibility.

No production entrypoint, mutation, consumer ACK, factory patch or raw export.
The existing public SDK fixture owns and closes all actual clients and stores.
"""
from decimal import Decimal
import hashlib
import json
import os
import re
import time
import urllib.request

SYSTEM_TOPIC = 'rmq_sys_REVIVE_LOG_FangcunMount'
BUFFER_NAMES = ('rocketmq_pop_offset_buffer_size', 'rocketmq_pop_checkpoint_buffer_size')


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


class OwnedPopControls:
    def __init__(self, run, admin, broker, project, manifest, proof, passed):
        self.run, self.admin, self.broker, self.project = run, admin, broker, project
        self.manifest, self.proof, self.passed = manifest, proof, passed
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
        self.url = 'http://127.0.0.1:' + bindings[0]['HostPort'] + '/metrics'

    def read(self, required):
        if self.url is None:
            self.configure()
        with urllib.request.urlopen(self.url, timeout=3) as response:
            require(response.status == 200, 'native_pop_scrape_failed')
            raw = response.read(8 * 1024 * 1024 + 1)
        return snapshot(raw.decode(), timing_required=required)

    def wait(self, predicate, *, required, budget):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            value = self.read(required)
            if predicate(value):
                return value
            time.sleep(.2)
        raise RuntimeError('native_pop_control_budget_exceeded')

    def __call__(self, stage, language):
        require(language in ('sdk-go', 'sdk-python') and stage in ('baseline', 'held', 'closed'), 'fixed_pop_control_stage_required')
        suffix = 'go' if language == 'sdk-go' else 'python'
        record = self.proof.setdefault(suffix, {})
        require(stage not in record, 'duplicate_pop_control_stage')
        if stage == 'baseline':
            record[stage] = self.wait(lambda v: zero(v, timing_required=self.observed_timer),
                                      required=self.observed_timer, budget=90)
        elif stage == 'held':
            require('baseline' in record, 'pop_baseline_required')
            routes = [row for row in self.manifest['routes'] if row['subscription'] == 'sdk-shared-' + suffix]
            groups = {row['consumer_group'] for row in routes}
            require(len(groups) == 1, 'one_actual_shared_pop_group_required')
            raw = self.admin('consumerConnection', '-g', next(iter(groups)))
            require(re.search(r'^ConsumeType: CONSUME_ACTIVELY$', raw, re.MULTILINE), 'actual_grpc_simple_consumer_required')
            record[stage] = self.wait(lambda v: v['timing'] is not None and v['timing'] > 0,
                                      required=False, budget=25)
            self.observed_timer = True
            record['connection_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
            self.passed('readable_pop_' + suffix + '_held_future_checkpoint_blocks_drain')
        else:
            require('held' in record and self.observed_timer, 'positive_future_checkpoint_control_required')
            record[stage] = self.wait(lambda v: zero(v, timing_required=True), required=True, budget=90)
            time.sleep(1)
            require(zero(self.read(True), timing_required=True), 'pop_responsibility_reappeared_after_sdk_close')
            self.passed('readable_pop_' + suffix + '_acked_and_closed_responsibility_zero')
