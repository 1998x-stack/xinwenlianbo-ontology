#!/usr/bin/env python3
"""B3 shadow-only ablation: B2 baseline vs embedding-backed event-centroid matching.

Synthetic --oracle-demo intentionally derives vectors from gold labels.
It tests plumbing only and MUST NOT be interpreted as algorithm performance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.event_clustering_v3 import blocked_pair_ids, cluster, parse_articles
from db.semantic_recall_b3 import (
    centroid_clusters, load_embeddings, semantic_pairs,
)
from eval.clustering_metrics import (
    bcubed_metrics, pair_retrieval_metrics, pairwise_metrics,
    partition_diagnostics, partition_from_gold,
)
from eval.run_event_ablations import load_inputs
from eval.reviewed_pair_scoring import membership_pairs, reviewed_pair_metrics
from eval.validate_annotations import validate_reviews


def oracle_demo_vectors(labels):
    """Deliberate label leakage, permitted for synthetic plumbing demos only."""
    groups = sorted(set(labels.values()))
    slots = {label: i for i, label in enumerate(groups)}
    return {nid: [1.0 if k == slots[label] else 0.0 for k in range(len(groups))]
            for nid, label in labels.items()}


def compare(items, embeddings, *, kind, gold=None, manifest=None, window_days=7,
            top_k=8, min_similarity=0.74, member_similarity=0.70,
            centroid_similarity=0.78, review_queue=None):
    ids = [a.news_id for a in items]
    gold_clusters = partition_from_gold(gold, ids) if gold is not None else None
    baseline, _ = cluster(items, variant="constrained", window_days=window_days)
    semantic = semantic_pairs(
        items, embeddings, window_days=window_days, top_k=top_k,
        min_similarity=min_similarity,
    )
    blocked = blocked_pair_ids(items, window_days=window_days)
    semantic_pairs_ids = {(e.left, e.right) for e in semantic}
    union = blocked | semantic_pairs_ids
    centroid_block_only = centroid_clusters(
        items, embeddings, candidate_pairs=blocked,
        window_days=window_days, min_member_similarity=member_similarity,
        min_centroid_similarity=centroid_similarity,
    )
    pred = centroid_clusters(
        items, embeddings, candidate_pairs=union,
        window_days=window_days, min_member_similarity=member_similarity,
        min_centroid_similarity=centroid_similarity,
    )

    def output(clusters):
        entry = {"diagnostics": partition_diagnostics(clusters, items)}
        if gold_clusters is None:
            entry["pairwise"] = None
            entry["bcubed"] = None
        else:
            entry["pairwise"] = pairwise_metrics(gold_clusters, clusters, ids)
            entry["bcubed"] = bcubed_metrics(gold_clusters, clusters, ids)
        return entry

    review_report = None
    if review_queue is not None:
        review_report = {
            "review_validation": validate_reviews(review_queue),
            "B2": reviewed_pair_metrics(review_queue, membership_pairs(baseline)),
            "B3_rule_candidates": reviewed_pair_metrics(review_queue, membership_pairs(centroid_block_only)),
            "B3_semantic_union": reviewed_pair_metrics(review_queue, membership_pairs(pred)),
        }
    return {
        "reviewed_pair_evaluation": review_report,
        "kind": kind,
        "warning": ("ORACLE-LABEL-LEAKAGE: no real-world metric"
                    if kind == "synthetic_oracle_demo"
                    else "Unreviewed historical dataset: quality metrics unavailable"
                    if gold is None else "Human-reviewed fixture: use held-out split for claims"),
        "embedding_provenance": manifest,
        "parameters": {
            "window_days": window_days, "top_k": top_k,
            "semantic_min_similarity": min_similarity,
            "min_member_similarity": member_similarity,
            "min_centroid_similarity": centroid_similarity,
        },
        "candidate_retrieval": {
            "baseline_pairs": len(blocked),
            "semantic_pairs": len(semantic_pairs_ids),
            "union_pairs": len(union),
            "semantic_only_additional_pairs": len(semantic_pairs_ids - blocked),
            "blocking_gold": pair_retrieval_metrics(gold_clusters, blocked, ids) if gold_clusters is not None else None,
            "semantic_gold": pair_retrieval_metrics(gold_clusters, semantic_pairs_ids, ids) if gold_clusters is not None else None,
            "union_gold": pair_retrieval_metrics(gold_clusters, union, ids) if gold_clusters is not None else None,
        },
        "B2_constrained": output(baseline),
        "B3_centroid_rule_candidates": output(centroid_block_only),
        "B3_semantic_centroid": output(pred),
        "published_to_production": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--input", type=Path)
    src.add_argument("--fixture", type=Path)
    parser.add_argument("--vectors", type=Path, help="Embeddings from build_embeddings_b3.py")
    parser.add_argument("--oracle-demo", action="store_true",
                        help="Synthetic fixture ONLY; uses gold labels to fabricate perfect vectors")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reviews", type=Path, help="Double-reviewed/adjudicated JSONL queue")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--min-similarity", type=float, default=0.74)
    parser.add_argument("--member-similarity", type=float, default=0.70)
    parser.add_argument("--centroid-similarity", type=float, default=0.78)
    args = parser.parse_args()
    if not args.vectors and not args.oracle_demo:
        parser.error("provide --vectors; or --oracle-demo with an explicit synthetic fixture")
    if args.vectors and args.oracle_demo:
        parser.error("cannot combine real vector input with oracle demo")
    if args.oracle_demo and not args.fixture:
        parser.error("--oracle-demo requires --fixture")
    if args.input and args.output and args.input.resolve() == args.output.resolve():
        parser.error("refusing to overwrite source data")

    source_path = args.fixture or args.input or (ROOT / "data" / "news_items.jsonl")
    if args.fixture:
        items, gold, kind = load_inputs(fixture=source_path)
    else:
        items, gold, kind = load_inputs(input_file=source_path)
    if args.oracle_demo:
        if kind != "synthetic":
            parser.error("oracle demo forbidden on human-reviewed or historical data")
        vectors = oracle_demo_vectors(gold)
        kind = "synthetic_oracle_demo"
        manifest = {"model_id": "ORACLE_GOLD_LABEL_LEAKAGE", "not_a_real_model": True}
    else:
        manifest_obj, vectors = load_embeddings(args.vectors, items, source_path=source_path)
        manifest = vars(manifest_obj)
    reviews = None
    if args.reviews:
        with args.reviews.open(encoding="utf-8") as handle:
            reviews = [json.loads(line) for line in handle if line.strip()]
        valid_ids = {item.news_id for item in items}
        if any(row["left_id"] not in valid_ids or row["right_id"] not in valid_ids for row in reviews):
            parser.error("review queue references articles missing from input snapshot")
    result = compare(
        items, vectors, kind=kind, gold=gold, manifest=manifest,
        review_queue=reviews,
        window_days=args.window_days, top_k=args.top_k,
        min_similarity=args.min_similarity,
        member_similarity=args.member_similarity,
        centroid_similarity=args.centroid_similarity,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_name(args.output.name + ".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
