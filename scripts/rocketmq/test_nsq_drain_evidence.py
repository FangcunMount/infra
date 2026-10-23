import copy
import contextlib
import io
import os
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import nsq_drain_evidence as drain

NOW = dt.datetime(2026, 10, 23, 12, 0, 30, tzinfo=dt.timezone.utc)


def fixtures():
    node = dict(node_id="serverd-nsqd", container_id="a"*64, container_started_at="2026-10-23T11:00:00.123456789Z", version="1.3.0", topics={"qs.events":["worker", "authz"]})
    channel = dict(channel_name="worker", depth=0, backend_depth=0, in_flight_count=0, deferred_count=0,
                   message_count=9, requeue_count=1, timeout_count=0, client_count=3, paused=False)
    other = dict(channel, channel_name="authz", message_count=5, client_count=1)
    data = dict(version="1.3.0", health="OK", start_time=1792753200, topics=[dict(topic_name="qs.events", depth=0, backend_depth=0, message_count=9, message_bytes=50, paused=False, channels=[channel, other])])
    capture = dict(node_id=node["node_id"], container_id=node["container_id"], container_started_at=node["container_started_at"], request_path=drain.STATS_PATH, captured_at="2026-10-23T12:00:10Z", stats=data)
    later = copy.deepcopy(capture);later["captured_at"] = "2026-10-23T12:00:25Z"
    manifest = dict(schema="m3-nsq-drain-inventory/v1", nodes=[node])
    captures = dict(schema="m3-nsq-drain-captures/v1", nodes=[dict(node_id=node["node_id"], captures=[capture, later])])
    return manifest, captures


class DrainTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.captures = fixtures()

    def run_gate(self):
        return drain.evaluate(self.manifest, self.captures, NOW)

    def latest(self):
        return self.captures["nodes"][0]["captures"][1]

    def test_full_empty_observation_does_not_authorize_cutover(self):
        original = copy.deepcopy((self.manifest, self.captures))
        result = self.run_gate()
        self.assertEqual(result["status"], "nsq_drain_observed")
        self.assertEqual((result["nodes"],result["topics"],result["channels"]),(1,1,2))
        self.assertFalse(result["cutover_authorized"])
        self.assertEqual(original, (self.manifest, self.captures))
        self.assertNotIn("qs.events", json.dumps(result))
        self.assertNotIn("worker", json.dumps(result))

    def test_topic_zero_does_not_hide_channel_responsibility(self):
        for field in ("depth", "backend_depth", "in_flight_count", "deferred_count"):
            with self.subTest(field=field):
                self.manifest, self.captures = fixtures()
                self.latest()["stats"]["topics"][0]["channels"][1][field] = 1
                with self.assertRaisesRegex(ValueError,"channel_responsibility"): self.run_gate()

    def test_backend_topic_backlog_blocks(self):
        self.latest()["stats"]["topics"][0]["backend_depth"] = 1
        with self.assertRaisesRegex(ValueError,"topic_backlog"): self.run_gate()

    def test_missing_extra_or_duplicate_subscription_blocks(self):
        for mutation in ("missing", "extra", "duplicate"):
            with self.subTest(mutation=mutation):
                self.manifest,self.captures = fixtures()
                channels = self.latest()["stats"]["topics"][0]["channels"]
                if mutation == "missing":channels.pop()
                elif mutation == "extra":channels.append(dict(channels[0],channel_name="forgotten"))
                else:channels[1] = copy.deepcopy(channels[0])
                with self.assertRaisesRegex(ValueError,"channel_inventory_changed"):self.run_gate()

    def test_empty_topics_missing_nodes_and_unfiltered_scope_required(self):
        self.latest()["stats"]["topics"] = []
        with self.assertRaisesRegex(ValueError,"topic_inventory_changed"):self.run_gate()
        self.manifest,self.captures = fixtures();self.captures["nodes"] = []
        with self.assertRaisesRegex(ValueError,"node_inventory_changed"):self.run_gate()
        self.manifest,self.captures = fixtures();self.latest()["request_path"] += "&topic=qs.events"
        with self.assertRaisesRegex(ValueError,"unfiltered_capture_required"):self.run_gate()

    def test_process_restart_and_same_second_container_restart_block(self):
        self.latest()["stats"]["start_time"] -= 1
        with self.assertRaisesRegex(ValueError,"process_restarted"):self.run_gate()
        self.manifest,self.captures = fixtures();self.latest()["container_started_at"]="2026-10-23T11:00:00.123456790Z"
        with self.assertRaisesRegex(ValueError,"process_restarted"):self.run_gate()

    def test_unknown_negative_bool_float_counter_blocks(self):
        for value in (None,-1,True,0.0,"0",2**64):
            with self.subTest(value=value):
                self.manifest,self.captures = fixtures();self.latest()["stats"]["topics"][0]["channels"][0]["deferred_count"] = value
                with self.assertRaisesRegex(ValueError,"invalid_counter"):self.run_gate()

    def test_activity_even_when_already_consumed_blocks(self):
        for key in ("message_count","message_bytes"):
            with self.subTest(key=key):
                self.manifest,self.captures = fixtures();self.latest()["stats"]["topics"][0][key] += 1
                with self.assertRaisesRegex(ValueError,"activity_between_captures"):self.run_gate()
        for key in ("message_count","timeout_count","requeue_count"):
            with self.subTest(key=key):
                self.manifest,self.captures = fixtures();self.latest()["stats"]["topics"][0]["channels"][0][key] += 1
                with self.assertRaisesRegex(ValueError,"activity_between_captures"):self.run_gate()

    def test_stale_short_reversed_future_or_unhealthy_capture_blocks(self):
        for when in ("2026-10-23T12:00:11Z","2026-10-23T12:00:09Z","2026-10-23T12:00:31Z","2026-10-23T11:59:00Z"):
            with self.subTest(when=when):
                self.manifest,self.captures = fixtures();self.latest()["captured_at"] = when
                with self.assertRaises(ValueError):self.run_gate()
        self.manifest,self.captures = fixtures();self.latest()["stats"]["health"]="NOK: private detail"
        with self.assertRaisesRegex(ValueError,"node_unhealthy"):self.run_gate()

    def test_inventory_not_vacuously_empty_and_raw_duplicate_keys_rejected(self):
        self.manifest["nodes"] = []
        with self.assertRaisesRegex(ValueError,"invalid_inventory"):self.run_gate()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"bad.json";path.write_text('{"nodes":[],"nodes":[]}')
            with self.assertRaisesRegex(ValueError,"duplicate_json_key"):drain.load(path)

    def test_missing_empty_channel_array_is_not_an_authoritative_empty_list(self):
        self.manifest["nodes"][0]["topics"]["qs.events"] = []
        for capture in self.captures["nodes"][0]["captures"]:
            capture["stats"]["topics"][0].pop("channels")
        with self.assertRaisesRegex(ValueError,"invalid_stats"):self.run_gate()

    def test_cli_private_atomic_output_and_redacted_refusal(self):
        now = dt.datetime.now(dt.timezone.utc)
        for index, capture in enumerate(self.captures["nodes"][0]["captures"]):
            capture["captured_at"] = (now-dt.timedelta(seconds=10 if index==0 else 1)).isoformat().replace("+00:00","Z")
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=root/"inventory.json";captures=root/"captures.json";output=root/"receipt.json"
            manifest.write_text(json.dumps(self.manifest));captures.write_text(json.dumps(self.captures))
            args=["gate","--inventory",str(manifest),"--captures",str(captures),"--output",str(output)]
            with mock.patch("sys.argv",args),contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(drain.main(),0)
            self.assertEqual(os.stat(output).st_mode & 0o777,0o600)
            receipt=output.read_bytes();self.assertFalse(json.loads(receipt)["cutover_authorized"])
            self.assertNotIn("qs.events",stdout.getvalue());self.assertNotIn("worker",stdout.getvalue())
            with mock.patch("sys.argv",args),contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(drain.main(),1)
            self.assertEqual(output.read_bytes(),receipt)
            self.assertNotIn(str(output),stdout.getvalue())

    def test_cumulative_counter_reset_not_a_clean_window(self):
        self.latest()["stats"]["topics"][0]["message_count"] = 0
        with self.assertRaisesRegex(ValueError,"activity_between_captures"):self.run_gate()

    def test_each_node_must_be_present_once(self):
        other = copy.deepcopy(self.manifest["nodes"][0]);other["node_id"]="another";other["container_id"]="b"*64
        self.manifest["nodes"].append(other)
        self.captures["nodes"].append(copy.deepcopy(self.captures["nodes"][0]))
        with self.assertRaisesRegex(ValueError,"node_inventory_changed"):self.run_gate()


if __name__ == "__main__":unittest.main()
