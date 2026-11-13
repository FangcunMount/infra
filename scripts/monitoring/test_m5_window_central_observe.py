import unittest

from m5_window_central_observe import (
    METRICS, OWNERS, active_targets, check_matrix, expected_targets, observe, scrape_time, utc,
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

    def full_observation(self, *, missing_at=None, active_age=0):
        targets = expected_targets(["172.20.0.114", "172.20.0.115"])
        end = 9000
        active_at = end + active_age

        def get(path, **params):
            if path == "/api/v1/targets":
                return {"activeTargets": [
                    dict(labels=dict(job=job, instance=instance), health="up",
                         lastScrape=utc(active_at - 1).replace("+00:00", "Z"))
                    for job, instance in sorted(targets)
                ]}
            self.assertEqual("/api/v1/query_range", path)
            self.assertEqual((end - 7200, end, 15), (params["start"], params["end"], params["step"]))
            selector = params["query"]
            is_timestamp = selector.startswith("timestamp(")
            metric = selector.removeprefix("timestamp(").split("{", 1)[0]
            identities = targets if metric == "up" else OWNERS
            points = range(params["start"], params["end"] + 1, params["step"])
            return dict(resultType="matrix", result=[
                dict(metric=dict(zip(KEYS, identity)), values=[
                    [point, str(point - 1 if is_timestamp else METRICS[metric])]
                    for point in points if not (metric == "up" and point == missing_at)
                ]) for identity in sorted(identities)
            ])

        return observe(get, targets, end, clock=lambda: active_at)

    def test_two_hours_pass_with_all_481_points_and_fresh_active_targets(self):
        report = self.full_observation()
        self.assertEqual(481, report["points"])
        self.assertEqual(7200, report["range_seconds"])
        self.assertTrue(report["passed"])
        self.assertFalse(report["execution_authorized"])

    def test_recovered_endpoint_does_not_hide_a_gap_older_than_30_minutes(self):
        report = self.full_observation(missing_at=5400)
        self.assertFalse(report["passed"])
        self.assertEqual([utc(5400)], [failure["at"] for failure in report["checks"]["up"]])
        self.assertFalse(any(report["active"].values()))

    def test_fresh_targets_cannot_certify_an_old_range_end(self):
        report = self.full_observation(active_age=36)
        self.assertEqual(36, report["end_age_seconds"])
        self.assertFalse(any(report["checks"].values()))
        self.assertFalse(any(report["active"].values()))
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
