from copy import deepcopy
import unittest

import test_servera_history_seam

import classify_servera_history as gate


class GapClassification(unittest.TestCase):
    def setUp(self):
        self.case = test_servera_history_seam.SeamTest()
        self.case.start, self.case.end, self.case.boundary = (1000, 1180, 1105)
        self.history = self.case.raw(
            "history", [1015, 1030, 1075, 1090, 1105, 1120, 1135]
        )
        self.source = deepcopy(self.history)
        self.source["route"] = "macmini"
        self.local = self.case.raw("candidate", [1105, 1120, 1135, 1150, 1165, 1180])
        self.merged = self.case.raw(
            "merged", [1015, 1030, 1075, 1090, 1105, 1120, 1135, 1150, 1165, 1180]
        )

    def run_check(self):
        return gate.classify(
            self.source,
            self.history,
            self.local,
            self.merged,
            self.case.boundary * 1000,
        )

    def test_original_gap_preserved(self):
        receipt = self.run_check()
        self.assertEqual(receipt["inherited_source_gap_count"], 22)
        self.assertEqual(receipt["unresolved_gap_count"], 0)
        self.assertFalse(receipt["pause_for_review"])

    def test_old_failure_value_preserved_without_claiming_zero(self):
        for receipt in (self.source, self.history, self.merged):
            receipt["responses"]["up"]["data"]["result"][0]["values"][0][1] = "0"
        actual = self.run_check()
        self.assertEqual(
            sum(len(row["preserved_source_nonhealthy"]) for row in actual["series"]), 1
        )
        self.assertFalse(actual["pause_for_review"])

    def test_candidate_hole_and_trailing_coverage_require_review(self):
        self.local = self.case.raw("candidate", [1105, 1120, 1135])
        self.merged = self.case.raw(
            "merged", [1015, 1030, 1075, 1090, 1105, 1120, 1135]
        )
        actual = self.run_check()
        self.assertEqual(actual["unresolved_gap_count"], 22)
        self.assertTrue(actual["pause_for_review"])

    def test_history_can_mask_candidate_sampling_gap(self):
        self.history = self.case.raw(
            "history", [1015, 1030, 1075, 1090, 1105, 1120, 1135, 1150]
        )
        self.source = deepcopy(self.history)
        self.source["route"] = "macmini"
        self.local = self.case.raw("candidate", [1105, 1150, 1165, 1180])
        receipt = self.run_check()
        self.assertEqual(receipt["unresolved_gap_count"], 0)
        self.assertEqual(receipt["candidate_local_gap_count"], 22)
        self.assertTrue(receipt["pause_for_review"])

    def test_candidate_series_start_late_is_visible_even_when_history_fills_it(self):
        self.history = self.case.raw(
            "history", [1015, 1030, 1075, 1090, 1105, 1120, 1135, 1150]
        )
        self.source = deepcopy(self.history)
        self.source["route"] = "macmini"
        self.local = self.case.raw("candidate", [1150, 1165, 1180])
        receipt = self.run_check()
        self.assertEqual(receipt["unresolved_gap_count"], 0)
        self.assertEqual(receipt["candidate_local_gap_count"], 22)
        self.assertTrue(receipt["pause_for_review"])

    def test_candidate_unhealthy_even_when_merged_is_exact(self):
        for receipt in (self.local, self.merged):
            receipt["responses"]["up"]["data"]["result"][0]["values"][-1][1] = "0"
        actual = self.run_check()
        self.assertEqual(actual["current_nonhealthy_count"], 1)
        self.assertTrue(actual["pause_for_review"])

    def test_archive_cannot_erase_or_invent_data(self):
        for index, changes in enumerate(("remove", "add")):
            with self.subTest(changes=changes):
                self.setUp()
                for receipt in (self.history, self.merged):
                    row = receipt["responses"]["up"]["data"]["result"][0]["values"]
                    if index == 0:
                        row.pop(1)
                    else:
                        row.insert(2, [1045, "1"])
                with self.assertRaisesRegex(
                    ValueError, "restored archive differs from source"
                ):
                    self.run_check()

    def test_warning_and_infos_block_regardless_of_status_and_samples(self):
        for field in ("warnings", "infos"):
            with self.subTest(field=field):
                self.setUp()
                self.merged["responses"]["up"][field] = ["possible partial results"]
                with self.assertRaisesRegex(ValueError, "returned annotations"):
                    self.run_check()

    def test_origin_receipt_must_be_local(self):
        for key in ("binding_before", "binding_after"):
            self.source[key]["remote_read"] = True
        with self.assertRaisesRegex(ValueError, "old collector local TSDB"):
            self.run_check()

    def test_old_failure_at_local_timestamp_remains_in_classification(self):
        for receipt in (self.source, self.history):
            values = receipt["responses"]["up"]["data"]["result"][0]["values"]
            next(row for row in values if row[0] == 1105)[1] = "0"
        result = self.run_check()
        (failure,) = [
            sample
            for row in result["series"]
            for sample in row["preserved_source_nonhealthy"]
        ]
        self.assertEqual(failure["value"], "0")
        self.assertFalse(failure["visible_in_merged"])
        self.assertFalse(result["pause_for_review"])


if __name__ == "__main__":
    unittest.main()
