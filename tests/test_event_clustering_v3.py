"""Independent S03/S05 invariants, regression cases, and historical smoke tests."""

import json
from pathlib import Path
import unittest

from db.event_clustering_v3 import (
    blocked_pair_ids, candidate_edges, cluster, constrained_clusters, legacy_clusters,
    parse_articles, preview_event_id,
)
from eval.clustering_metrics import (
    bcubed_metrics, label_partition, pairwise_metrics, pair_retrieval_metrics, partition_from_gold,
)
from eval.run_event_ablations import load_inputs, run_ablations
from eval.make_annotation_queue import make_queue

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "eval" / "datasets" / "synthetic_event_gold.json"


class EventClusteringTests(unittest.TestCase):
    def setUp(self):
        self.items, self.labels, self.kind = load_inputs(fixture=FIXTURE)
        self.by_name = {a.news_id: a for a in self.items}

    def test_fixture_is_explicitly_synthetic_and_partition_is_complete(self):
        self.assertEqual(self.kind, "synthetic")
        self.assertEqual(set(self.by_name), set(self.labels))
        self.assertGreaterEqual(len(self.items), 15)

    def test_no_generic_digest_or_same_topic_cross_region_false_merges(self):
        result, _ = cluster(self.items, variant="constrained")
        assignment = label_partition(result, self.by_name)
        self.assertNotEqual(assignment["g1"], assignment["h1"])
        self.assertNotEqual(assignment["a1"], assignment["b1"])
        self.assertNotEqual(assignment["e1"], assignment["f1"])
        self.assertNotEqual(assignment["a1"], assignment["i1"])

    def test_repeatability_and_global_id_uniqueness(self):
        first, first_edges = cluster(self.items)
        shuffled, shuffled_edges = cluster(list(reversed(self.items)))
        self.assertEqual(first, shuffled)
        self.assertEqual(first_edges, shuffled_edges)
        self.assertEqual(len({preview_event_id(g) for g in first}), len(first))
        self.assertEqual(first, constrained_clusters(self.items, first_edges))

    def test_legacy_chain_bridge_detectable_on_synthetic(self):
        baseline = legacy_clusters(self.items)
        self.assertEqual(sum(map(len, baseline)), len(self.items))
        result = run_ablations(self.items, gold=self.labels, kind=self.kind)
        self.assertEqual(set(result["variants"]), {"legacy", "connected", "constrained"})
        self.assertFalse(result["gold_quality_valid_for_real_world"])
        self.assertIsNotNone(result["variants"]["legacy"]["gold_pairwise"])
        self.assertIsNotNone(result["variants"]["constrained"]["gold_bcubed"])

    def test_invalid_variant_score_and_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "unknown event algorithm"):
            cluster(self.items, variant="nonexistent")
        with self.assertRaisesRegex(ValueError, "invalid clustering parameters"):
            candidate_edges(self.items, minimum_score=-0.5)
        with self.assertRaisesRegex(ValueError, "duplicate news_id"):
            parse_articles([{"news_id": "x", "title": "A", "broadcast_date": "2026-01-01"}] * 2)

    def test_scoring_rejects_dangling_or_duplicate_partitions(self):
        gold = partition_from_gold(self.labels, [a.news_id for a in self.items])
        with self.assertRaisesRegex(ValueError, "missing event members"):
            label_partition(gold[:-1], self.by_name)
        with self.assertRaisesRegex(ValueError, "unknown or duplicated event membership"):
            label_partition(gold + [("a1",)], self.by_name)

    def test_blocking_recall_has_explicit_gold_metric(self):
        gold = partition_from_gold(self.labels, self.by_name)
        retrieval = pair_retrieval_metrics(gold, blocked_pair_ids(self.items), self.by_name)
        self.assertGreaterEqual(retrieval["retrieved_pairs"], retrieval["tp"])
        self.assertTrue(0 <= retrieval["recall"] <= 1)
        pair = pair_retrieval_metrics([("a","b","c")], {("a","b")}, ("a","b","c"))
        self.assertEqual(pair["recall"], round(1/3, 6))

    def test_stratified_review_queue_is_unlabeled_and_reproducible(self):
        first = make_queue(self.items, limit=12, seed=17)
        self.assertEqual(first, make_queue(list(reversed(self.items)), limit=12, seed=17))
        self.assertEqual(len({(r["left_id"],r["right_id"]) for r in first}),len(first))
        self.assertTrue(all(r["reviewer_1"]["label"] is None for r in first))
        self.assertTrue(all(r["reviewer_2"]["label"] is None for r in first))
        self.assertIn("model_positive", {r["sampling_stratum"] for r in first})
        self.assertIn("topical_unmatched", {r["sampling_stratum"] for r in first})

    def test_synthetic_metric_known_value(self):
        ids = ["a", "b", "c"]
        gold = [("a", "b", "c")]
        pred = [("a", "b"), ("c",)]
        pair = pairwise_metrics(gold, pred, ids)
        self.assertEqual((pair["tp"], pair["fp"], pair["fn"]), (1, 0, 2))
        self.assertEqual(pair["recall"], round(1 / 3, 6))
        self.assertEqual(pair["f1"], 0.5)
        bcubed = bcubed_metrics(gold, pred, ids)
        self.assertEqual(bcubed["precision"], 1.0)
        self.assertAlmostEqual(bcubed["recall"], 5 / 9, places=6)

    def test_partial_gold_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "gold annotations and input IDs"):
            partition_from_gold({"a1": "event-a"}, self.by_name)

    def test_existing_historical_snapshot_is_read_only(self):
        path = ROOT / "data" / "news_items.jsonl"
        self.assertTrue(path.is_file())
        articles, gold, kind = load_inputs(input_file=path)
        self.assertIsNone(gold)
        report = run_ablations(articles, kind=kind)
        self.assertEqual(report["dataset_kind"], "unlabeled_historical")
        for item in report["variants"].values():
            self.assertEqual(item["diagnostics"]["items"], len(articles))
            self.assertIsNone(item["gold_pairwise"])
            self.assertEqual(
                sum(int(k) * v for k, v in item["diagnostics"]["size_histogram"].items()),
                len(articles),
            )


if __name__ == "__main__":
    unittest.main()
