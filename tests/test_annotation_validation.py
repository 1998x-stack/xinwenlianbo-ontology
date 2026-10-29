"""Test adjudication gates without confusing pair annotations with full gold."""
import unittest
from eval.validate_annotations import validate_reviews


def pair(a=None, b=None, adjud=None, adjud_reviewer=None):
    return {
        "left_id": "a", "right_id": "b",
        "reviewer_1": {"id": "r1" if a is not None else None, "label": a},
        "reviewer_2": {"id": "r2" if b is not None else None, "label": b},
        "adjudication": {"label": adjud, "reviewer": adjud_reviewer},
    }


class AnnotationValidationTests(unittest.TestCase):
    def test_unreviewed_is_not_ground_truth(self):
        stats = validate_reviews([pair()])
        self.assertEqual(stats["unreviewed"], 1)
        self.assertEqual(stats["ready_definitive_pairs"], 0)
        self.assertIsNone(stats["cohens_kappa"])

    def test_disagreement_requires_explicit_adjudicator(self):
        row = pair("SAME_EVENT", "DIFFERENT_EVENT")
        self.assertEqual(validate_reviews([row])["needs_adjudication"], 1)
        row["adjudication"] = {"label": "RELATED_NOT_SAME", "reviewer": "r3"}
        self.assertEqual(validate_reviews([row])["ready_definitive_pairs"], 1)

    def test_agreement_and_unsure_are_distinct(self):
        self.assertEqual(validate_reviews([pair("SAME_EVENT", "SAME_EVENT")])["agreed_and_definitive"], 1)
        self.assertEqual(validate_reviews([pair("UNSURE", "UNSURE")])["ready_definitive_pairs"], 0)

    def test_reject_invalid_or_duplicate_review(self):
        with self.assertRaisesRegex(ValueError, "unsupported annotation label"):
            validate_reviews([pair("UNKNOWN", "SAME_EVENT")])
        with self.assertRaisesRegex(ValueError, "duplicate review pair"):
            validate_reviews([pair(), pair()])
        bad = pair("SAME_EVENT", "DIFFERENT_EVENT")
        bad["reviewer_2"]["id"] = "r1"
        with self.assertRaisesRegex(ValueError, "distinct reviewer"):
            validate_reviews([bad])


if __name__ == "__main__":
    unittest.main()
