"""No artificial human gold: full pair coverage and two reviewer agreement."""

import hashlib
import json
from pathlib import Path
import unittest

from eval.build_complete_review_queue import complete_review_queue
from eval.build_reviewed_gold import build_gold
from eval.select_review_subset import select

ROOT = Path(__file__).resolve().parents[1]


class ReviewedGoldTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"news_id": "a", "title": "甲省防汛情况更新", "broadcast_date": "2026-06-07"},
            {"news_id": "b", "title": "甲省防汛后续通报", "broadcast_date": "2026-06-08"},
            {"news_id": "c", "title": "乙省发布科技规划", "broadcast_date": "2026-06-09"},
        ]
        self.ids = ["a", "b", "c"]
        self.queue = complete_review_queue(self.records, self.ids)
        self.digest = hashlib.sha256(b"fixture").hexdigest()
        for row in self.queue:
            row["reviewer_1"].update(id="reviewer-A", label="DIFFERENT_EVENT")
            row["reviewer_2"].update(id="reviewer-B", label="DIFFERENT_EVENT")
        first = next(row for row in self.queue if set([row["left_id"], row["right_id"]]) == {"a", "b"})
        first["reviewer_1"]["label"] = "SAME_EVENT"
        first["reviewer_2"]["label"] = "SAME_EVENT"

    def test_create_complete_gold(self):
        fixture = build_gold(
            self.records, self.queue, self.ids,
            source_sha=self.digest, guideline_version="test-v1",
        )
        self.assertEqual(fixture["reviewed_pairs"], 3)
        self.assertEqual(fixture["labels"]["a"], fixture["labels"]["b"])
        self.assertNotEqual(fixture["labels"]["a"], fixture["labels"]["c"])
        self.assertEqual(fixture["fixture_type"], "human_reviewed")
        self.assertEqual(fixture["reviewer_count"], 2)

    def test_do_not_promote_unreviewed_or_partial_review(self):
        with self.assertRaisesRegex(ValueError, "exhaustive pair review"):
            build_gold(self.records, self.queue[:-1], self.ids,
                       source_sha=self.digest, guideline_version="test-v1")
        self.queue[0]["reviewer_1"]["label"] = None
        with self.assertRaisesRegex(ValueError, "not conclusively reviewed"):
            build_gold(self.records, self.queue, self.ids,
                       source_sha=self.digest, guideline_version="test-v1")

    def test_reject_transitivity_conflict(self):
        for row in self.queue:
            if set((row["left_id"], row["right_id"])) == {"b", "c"}:
                row["reviewer_1"]["label"] = "SAME_EVENT"
                row["reviewer_2"]["label"] = "SAME_EVENT"
        with self.assertRaisesRegex(ValueError, "contradictory"):
            build_gold(self.records, self.queue, self.ids,
                       source_sha=self.digest, guideline_version="test-v1")

    def test_reject_stale_review_snapshot(self):
        self.queue[0]["source"]["left_title"] = "incorrect article title"
        with self.assertRaisesRegex(ValueError, "source snapshot mismatch"):
            build_gold(self.records, self.queue, self.ids,
                       source_sha=self.digest, guideline_version="test-v1")

    def test_reproducible_selection_and_no_auto_labels(self):
        self.assertEqual(select(self.records, count=3), select(list(reversed(self.records)), count=3))
        fresh = complete_review_queue(self.records, self.ids)
        self.assertEqual(len(fresh), 3)
        self.assertTrue(all(row["reviewer_1"]["label"] is None for row in fresh))
        self.assertTrue(all(row["reviewer_2"]["label"] is None for row in fresh))


if __name__ == "__main__":
    unittest.main()
