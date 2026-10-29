"""Review-evaluation tests: abstain on unreviewed, never auto-negative."""
import unittest
from eval.reviewed_pair_scoring import reviewed_pair_metrics, membership_pairs


def record(left, right, one=None, two=None, *, stratum="model_positive", adjud=None):
    return {
        "left_id": left, "right_id": right, "sampling_stratum": stratum,
        "reviewer_1": {"id": "annotator-A" if one is not None else None, "label": one},
        "reviewer_2": {"id": "annotator-B" if two is not None else None, "label": two},
        "adjudication": {"label": adjud, "reviewer": "arbiter" if adjud else None},
    }


class ReviewedPairScoringTests(unittest.TestCase):
    def test_unreviewed_not_negative_and_null_scores(self):
        report = reviewed_pair_metrics([record("a", "b")], {("a", "b")})
        self.assertEqual(report["unresolved_pairs"], 1)
        self.assertEqual(report["overall_reviewed_sample"]["n"], 0)
        self.assertIsNone(report["overall_reviewed_sample"]["f1"])

    def test_scoring_resolved_pairs_only(self):
        queue = [
            record("a", "b", "SAME_EVENT", "SAME_EVENT"),
            record("a", "c", "DIFFERENT_EVENT", "DIFFERENT_EVENT", stratum="random_control"),
            record("b", "c", "SAME_EVENT", "DIFFERENT_EVENT", adjud="RELATED_NOT_SAME"),
            record("a", "d", "UNSURE", "UNSURE"),
        ]
        predicted = membership_pairs([("a", "b", "c"), ("d",)])
        report = reviewed_pair_metrics(queue, predicted)
        observed = report["overall_reviewed_sample"]
        self.assertEqual((observed["tp"], observed["fp"], observed["fn"], observed["tn"]), (1, 2, 0, 0))
        self.assertEqual(report["unresolved_pairs"], 1)
        self.assertIn("random_control", report["by_stratum"])

    def test_disagreement_without_adjudication_excluded(self):
        queue = [record("a", "b", "SAME_EVENT", "DIFFERENT_EVENT")]
        report = reviewed_pair_metrics(queue, set())
        self.assertEqual(report["unresolved_pairs"], 1)

    def test_duplicate_review_queue_or_cluster_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            reviewed_pair_metrics([record("a", "b"), record("b", "a")], set())
        with self.assertRaisesRegex(ValueError, "duplicate cluster"):
            membership_pairs([("a", "b"), ("b", "c")])


if __name__ == "__main__":
    unittest.main()
