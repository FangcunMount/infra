import unittest

from m5_window_central_observe import (
    OWNERS, active_targets, check_matrix, expected_targets, observe, scrape_time, utc,
)


KEYS = ("job", "instance", "owner")
POINT = 300


def matrix(identities, value, extra=None):
    return dict(resultType="matrix", result=[
        dict(metric={**dict(zip(KEYS, identity)), **(extra or {})}, values=[[POINT, str(value)]])
        for identity in sorted(identities)
    ])


class CentralObserverTest(unittest.TestCase):
    def check(self, values, source_times):
        return check_matrix(values, source_times, [POINT], KEYS, OWNERS, 1)

    def test_all_four_named_owner_samples_pass(self):
        self.assertEqual([], self.check(matrix(OWNERS, 1), matrix(OWNERS, 285)))

    def test_duplicate_owner_cannot_replace_a_missing_owner(self):
        duplicate = ("qs-apiserver", "qs-apiserver:8080", "qs.mysql")
        missing = ("iam", "iam-apiserver:9080", "iam.mysql")
        measured = matrix(OWNERS - {missing}, 1)
        measured["result"].extend(matrix({duplicate}, 1, {"replica": "other"})["result"])
        self.assertEqual(4, len(measured["result"]))
        with self.assertRaisesRegex(ValueError, "duplicate series"):
            self.check(measured, matrix(OWNERS - {missing}, 285))

    def test_wrong_job_and_instance_cannot_supply_a_named_owner(self):
        removed = ("iam", "iam-apiserver:9080", "iam.mysql")
        wrong = ("qs-ai", "qs-ai-api:8000", "iam.mysql")
        observed = (OWNERS - {removed}) | {wrong}
        failure, = self.check(matrix(observed, 1), matrix(observed, 285))
        self.assertEqual([removed], failure["missing"])
        self.assertEqual([wrong], failure["unexpected"])

    def test_stale_future_unavailable_and_missing_timestamp_fail(self):
        values = matrix(OWNERS, 0)
        source_times = matrix(OWNERS, 264)
        source_times["result"].pop()
        source_times["result"][0]["values"][0][1] = "301"
        failure, = self.check(values, source_times)
        self.assertEqual(sorted(OWNERS), failure["wrong"])
        self.assertEqual(sorted(OWNERS), failure["stale"])

    def test_prometheus_nanosecond_scrape_times_are_portable(self):
        self.assertEqual(285.123456, scrape_time("1970-01-01T00:04:45.123456789Z"))
        self.assertEqual(285.0, scrape_time("1970-01-01T00:04:45Z"))

    def test_named_collection_target_cannot_be_replaced_by_an_equal_count(self):
        targets = expected_targets(["172.20.0.114", "172.20.0.115"])
        removed = ("qs-collection-server", "172.20.0.114:8080")
        wrong = ("qs-collection-server", "172.20.0.116:8080")
        current = {"activeTargets": [
            dict(labels=dict(job=job, instance=instance), health="up", lastScrape=utc(285).replace("+00:00", "Z"))
            for job, instance in (targets - {removed}) | {wrong}
        ]}
        observed = active_targets(current, targets, POINT)
        self.assertEqual([removed], observed["missing"])
        self.assertEqual([wrong], observed["unexpected"])
        self.assertEqual([], observed["unhealthy_or_stale"])

    def test_explicit_qs_source_retains_all_other_target_and_owner_identities(self):
        addresses = ["172.20.0.114", "172.20.0.115"]
        original = expected_targets(addresses)
        candidate = expected_targets(addresses, "7014c24db0c6b57c130112752857b2bec0b9bc7d")
        self.assertEqual({("qs-worker", f"qs-m5-7014c24db0c6-worker-{n}") for n in range(1, 4)},
                         candidate - original)
        self.assertEqual(3, len(original - candidate))
        self.assertEqual(10, len(candidate))
        with self.assertRaisesRegex(ValueError, "full lowercase QS source"):
            expected_targets(addresses, "7014c24db0c6")

    def test_two_hour_range_uses_481_points_and_rejects_missing_samples(self):
        def no_samples(path, **params):
            if path == "/api/v1/targets":
                return {"activeTargets": []}
            self.assertEqual((0, 7200, 15), tuple(params[key] for key in ("start", "end", "step")))
            return {"resultType": "matrix", "result": []}

        targets = expected_targets(["172.20.0.114", "172.20.0.115"])
        receipt = observe(no_samples, targets, 7200, lambda: 7200, range_seconds=7200)
        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["execution_authorized"])
        self.assertEqual(481, receipt["points"])
        self.assertTrue(all(len(failures) == 481 for failures in receipt["checks"].values()))


if __name__ == "__main__":
    unittest.main()
