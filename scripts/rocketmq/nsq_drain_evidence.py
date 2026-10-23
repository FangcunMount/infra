#!/usr/bin/env python3
"""Offline NSQ 1.3.0 drain observation, never a cutover authorization.

Consumes two unfiltered /stats?format=json&include_clients=false&include_mem=false
captures per frozen node. Does not contact NSQ, remove channels, acknowledge
messages or infer that HTTP publishers/relays/business work have stopped.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from audit_transaction_limit import write_private

MAX_BYTES = 4 * 1024 * 1024
NAME = re.compile(r"[A-Za-z0-9_.-]+(?:#ephemeral)?")
SHA = re.compile(r"[0-9a-f]{64}")
UTC = dt.timezone.utc
STATS_PATH = "/stats?format=json&include_clients=false&include_mem=false"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def name(value):
    require(isinstance(value, str) and 1 <= len(value) <= 64 and NAME.fullmatch(value), "invalid_inventory")
    return value


def counter(value):
    require(type(value) is int and 0 <= value <= 2**64-1, "invalid_counter")
    return value


def stamp(value):
    require(isinstance(value, str) and value.endswith("Z"), "invalid_capture_time")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
        require(parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0), "invalid_capture_time")
        return parsed
    except ValueError:
        raise ValueError("invalid_capture_time") from None


def inventory(raw):
    require(isinstance(raw, dict) and raw.get("schema") == "m3-nsq-drain-inventory/v1", "invalid_inventory")
    nodes = raw.get("nodes")
    require(isinstance(nodes, list) and 1 <= len(nodes) <= 32, "invalid_inventory")
    result = {}
    for node in nodes:
        require(isinstance(node, dict), "invalid_inventory")
        identity = name(node.get("node_id"))
        require(identity not in result and isinstance(node.get("container_id"), str) and SHA.fullmatch(node["container_id"]), "invalid_inventory")
        require(node.get("version") == "1.3.0", "unsupported_version")
        stamp(node.get("container_started_at"))
        topics = node.get("topics")
        require(isinstance(topics, dict) and 1 <= len(topics) <= 1024, "invalid_inventory")
        for topic, channels in topics.items():
            name(topic)
            require(isinstance(channels, list) and len(channels) <= 1024, "invalid_inventory")
            for channel in channels:
                name(channel)
            require(len(set(channels)) == len(channels), "invalid_inventory")
        result[identity] = node
    return result


def normalize(capture, expected):
    require(isinstance(capture, dict) and capture.get("node_id") == expected["node_id"] and capture.get("container_id") == expected["container_id"], "node_identity_changed")
    require(capture.get("request_path") == STATS_PATH, "unfiltered_capture_required")
    require(capture.get("container_started_at") == expected["container_started_at"], "process_restarted")
    observed = stamp(capture.get("captured_at"))
    require(stamp(expected["container_started_at"]) <= observed, "invalid_process_identity")
    data = capture.get("stats")
    require(isinstance(data, dict) and data.get("version") == expected["version"], "unsupported_version")
    require(data.get("health") == "OK", "node_unhealthy")
    started = counter(data.get("start_time"))
    require(0 < started <= observed.timestamp(), "invalid_process_identity")
    topics = data.get("topics")
    require(isinstance(topics, list) and len(topics) == len(expected["topics"]), "topic_inventory_changed")
    normalized = {}
    for topic in topics:
        require(isinstance(topic, dict), "invalid_stats")
        key = name(topic.get("topic_name"))
        require(key in expected["topics"] and key not in normalized, "topic_inventory_changed")
        require(type(topic.get("paused")) is bool, "invalid_stats")
        for field in ("depth", "backend_depth"):
            require(counter(topic.get(field)) == 0, "topic_backlog")
        counts = [counter(topic.get(field)) for field in ("message_count", "message_bytes")]
        channels = topic.get("channels")
        # Pinned NSQ marshals a nil empty channel slice as null.
        if channels is None:
            channels = []
        require(isinstance(channels, list) and len(channels) == len(expected["topics"][key]), "channel_inventory_changed")
        by_channel = {}
        for channel in channels:
            require(isinstance(channel, dict), "invalid_stats")
            ch = name(channel.get("channel_name"))
            require(ch in expected["topics"][key] and ch not in by_channel, "channel_inventory_changed")
            require(type(channel.get("paused")) is bool, "invalid_stats")
            for field in ("depth", "backend_depth", "in_flight_count", "deferred_count"):
                require(counter(channel.get(field)) == 0, "channel_responsibility")
            counter(channel.get("client_count"))  # Connected consumers may still be present.
            by_channel[ch] = tuple(counter(channel.get(field)) for field in ("message_count", "requeue_count", "timeout_count"))
        normalized[key] = (counts, by_channel)
    return observed, started, normalized


def evaluate(manifest, captures, now):
    expected = inventory(manifest)
    require(isinstance(captures, dict) and captures.get("schema") == "m3-nsq-drain-captures/v1", "invalid_capture")
    records = captures.get("nodes")
    require(isinstance(records, list) and len(records) == len(expected), "node_inventory_changed")
    seen, latest = set(), None
    require(now.tzinfo is not None, "invalid_capture_time")
    for record in records:
        require(isinstance(record, dict), "invalid_capture")
        identity = record.get("node_id")
        require(isinstance(identity, str) and identity in expected and identity not in seen, "node_inventory_changed")
        seen.add(identity)
        pair = record.get("captures")
        require(isinstance(pair, list) and len(pair) == 2, "two_captures_required")
        before, after = (normalize(c, expected[identity]) for c in pair)
        interval = (after[0] - before[0]).total_seconds()
        require(5 <= interval <= 60 and 0 <= (now-after[0]).total_seconds() <= 15, "stale_or_short_observation")
        require(before[1] == after[1], "process_restarted")
        require(before[2] == after[2], "activity_between_captures")
        latest = max(latest or after[0], after[0])
    return dict(schema="m3-nsq-drain-observation/v1", status="nsq_drain_observed", nodes=len(seen),
                topics=sum(len(n["topics"]) for n in expected.values()),
                channels=sum(len(c) for n in expected.values() for c in n["topics"].values()),
                observed_at=latest.isoformat(), read_only=True, cutover_authorized=False,
                external_requirements=["frozen node/channel inventory independently verified", "old HTTP/TCP publishers and relays stopped", "in-flight business and receipts resolved", "future schedules explicitly handed off", "named cutover approval"])


def load(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES+1)
    require(len(raw) <= MAX_BYTES, "input_too_large")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique), hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest, manifest_hash = load(args.inventory)
        captures, capture_hash = load(args.captures)
        result = evaluate(manifest, captures, dt.datetime.now(UTC))
        result.update(inventory_sha256=manifest_hash, captures_sha256=capture_hash)
        write_private(args.output, result)
    except (ValueError, TypeError, KeyError, OSError, OverflowError):
        print(json.dumps(dict(status="unavailable_or_not_drained", read_only=True, cutover_authorized=False)))
        return 1
    print(json.dumps(dict(status=result["status"], nodes=result["nodes"], read_only=True, cutover_authorized=False)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
