"""Pure-data event diagnostic regression cases."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from event_quality import assess


class EventQualityTests(unittest.TestCase):
    def test_giant_cluster_is_flagged_without_claiming_accuracy(self):
        news = [{"news_id": f"n{i}"} for i in range(5)]
        events = [
            {"event_id": "e0", "items": [{"news_id": f"n{i}"} for i in range(4)]},
            {"event_id": "e1", "items": [{"news_id": "n4"}]},
        ]
        report = assess(events, news)
        self.assertEqual(report["largest_event_size"], 4)
        self.assertEqual(report["largest_event_share"], 0.8)
        self.assertTrue(report["requires_overmerge_review"])
        self.assertEqual(report["dangling_memberships"], 0)

    def test_invalid_references_and_unassigned_news(self):
        report = assess(
            [{"event_id": "x", "items": [{"news_id": "unknown"}]}],
            [{"news_id": "a"}, {"news_id": "b"}],
        )
        self.assertEqual(report["dangling_memberships"], 1)
        self.assertEqual(report["unassigned_news"], 2)

    def test_duplicate_members_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate membership"):
            assess([{"event_id": "e", "items": [{"news_id": "n"}, {"news_id": "n"}]}],
                   [{"news_id": "n"}])


if __name__ == "__main__":
    unittest.main()
