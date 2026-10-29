"""B3 semantic recall and centroid safety tests (no model/network needed)."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from db.event_clustering_v3 import parse_articles
from db.semantic_recall_b3 import (
    centroid_clusters, cosine, input_sha256, load_embeddings,
    pair_compatible, semantic_pairs,
)
from eval.run_b3_experiment import compare, oracle_demo_vectors
from eval.run_event_ablations import load_inputs

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "eval" / "datasets" / "synthetic_event_gold.json"


class B3Tests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"news_id": "a", "broadcast_date": "2026-09-01",
             "title": "东方号火箭发射成功", "topics": [{"name": "科技"}],
             "organizations": [{"name": "中国航天研究院"}], "keywords": ["火箭"]},
            {"news_id": "b", "broadcast_date": "2026-09-02",
             "title": "载人飞船发射进入预定轨道", "topics": [{"name": "航天"}],
             "organizations": [{"name": "中国航天研究院"}], "keywords": ["航天器"]},
            {"news_id": "c", "broadcast_date": "2026-09-02",
             "title": "乙省火箭发射成功", "topics": [{"name": "科技"}],
             "organizations": [{"name": "乙省航空组织"}], "keywords": ["火箭"]},
            {"news_id": "d", "broadcast_date": "2026-09-02",
             "title": "国际联播快讯", "topics": [{"name": "科技"}],
             "organizations": [{"name": "中国航天研究院"}], "keywords": ["火箭"]},
            {"news_id": "e", "broadcast_date": "2026-09-02",
             "title": "中国航天研究院签署火箭协议", "topics": [{"name": "科技"}],
             "organizations": [{"name": "中国航天研究院"}], "keywords": ["火箭"]},
        ]
        self.items = parse_articles(self.rows)
        self.vec = {"a": [1, 0, 0], "b": [0.99, 0.01, 0],
                    "c": [1, 0, 0], "d": [1, 0, 0], "e": [1, 0, 0]}

    def test_semantic_recall_finds_nonlexical_pair_without_conflicts(self):
        edges = semantic_pairs(self.items, self.vec, min_similarity=0.75)
        pairs = {(e.left, e.right) for e in edges}
        self.assertIn(("a", "b"), pairs)
        self.assertNotIn(("a", "c"), pairs)
        self.assertNotIn(("a", "d"), pairs)
        self.assertNotIn(("a", "e"), pairs)

    def test_centroid_needs_candidate_support_and_is_deterministic(self):
        edges = semantic_pairs(self.items, self.vec)
        pairs = [(edge.left, edge.right) for edge in edges]
        groups = centroid_clusters(self.items, self.vec, candidate_pairs=pairs)
        together = [set(g) for g in groups if "a" in g][0]
        self.assertEqual(together, {"a", "b"})
        self.assertEqual(groups, centroid_clusters(list(reversed(self.items)), self.vec, candidate_pairs=pairs))
        split = centroid_clusters(self.items, self.vec, candidate_pairs=[])
        self.assertEqual(len(split), len(self.items))

    def test_model_similarity_alone_does_not_override_actor_action_gates(self):
        a, b, c, d, e = self.items
        self.assertTrue(pair_compatible(a, b))
        self.assertFalse(pair_compatible(a, c))
        self.assertFalse(pair_compatible(a, d))
        self.assertFalse(pair_compatible(a, e))
        with self.assertRaisesRegex(ValueError, "invalid semantic recall"):
            semantic_pairs(self.items, self.vec, top_k=0)
        with self.assertRaisesRegex(ValueError, "zero-norm"):
            semantic_pairs(self.items, {**self.vec, "a": [0, 0, 0]})
        with self.assertRaisesRegex(ValueError, "non-finite"):
            semantic_pairs(self.items, {**self.vec, "a": [float("nan"), 0, 1]})

    def test_provenance_and_id_dimension_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "news.jsonl"
            source.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.rows), encoding="utf-8")
            path = Path(folder) / "vectors.json"
            manifest = {
                "format_version": 1, "model_id": "test-mock",
                "revision": "test-commit", "input_sha256": input_sha256(source),
                "text_template": "unit-test:v1", "dimension": 3, "vectors": self.vec,
            }
            path.write_text(json.dumps(manifest), encoding="utf-8")
            metadata, result = load_embeddings(path, self.items, source_path=source)
            self.assertEqual(metadata.dimension, 3)
            self.assertEqual(len(result), 5)
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source input changed"):
                load_embeddings(path, self.items, source_path=source)
            source.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.rows), encoding="utf-8")
            manifest["vectors"].pop("b")
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "embedding IDs"):
                load_embeddings(path, self.items, source_path=source)

    def test_oracle_demo_explicitly_marks_label_leakage(self):
        articles, labels, kind = load_inputs(fixture=SYNTHETIC)
        self.assertEqual(kind, "synthetic")
        vectors = oracle_demo_vectors(labels)
        report = compare(articles, vectors, kind="synthetic_oracle_demo", gold=labels)
        self.assertIn("ORACLE-LABEL-LEAKAGE", report["warning"])
        self.assertFalse(report["published_to_production"])
        self.assertEqual(report["B3_semantic_centroid"]["diagnostics"]["items"], len(articles))
        self.assertIsNotNone(report["candidate_retrieval"]["union_gold"])

    def test_window_blocks_distant_event_even_for_identical_vectors(self):
        rows = [dict(self.rows[0]), dict(self.rows[1])]
        rows[1]["broadcast_date"] = "2026-11-20"
        articles = parse_articles(rows)
        vectors = {"a": [1, 0], "b": [1, 0]}
        self.assertEqual(semantic_pairs(articles, vectors), [])
        self.assertEqual(len(centroid_clusters(articles, vectors, candidate_pairs=[])), 2)


if __name__ == "__main__":
    unittest.main()
