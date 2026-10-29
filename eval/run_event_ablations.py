#!/usr/bin/env python3
"""Offline event-clustering ablation runner; READ-ONLY and NO LLM calls.

Usage:
  python eval/run_event_ablations.py
  python eval/run_event_ablations.py --fixture eval/datasets/synthetic_event_gold.json
  python eval/run_event_ablations.py --input data/news_items.jsonl --output /tmp/ablations.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.event_clustering_v3 import blocked_pair_ids, cluster, parse_articles, preview_event_id
from eval.clustering_metrics import (
    bcubed_metrics, pairwise_metrics, pair_retrieval_metrics, partition_diagnostics, partition_from_gold,
)


def load_inputs(*, input_file=None, fixture=None):
    """Fixture must identify its provenance: synthetic or human-reviewed."""
    if (input_file is None) == (fixture is None):
        raise ValueError("select exactly one input source")
    if fixture:
        document = json.loads(Path(fixture).read_text(encoding="utf-8"))
        kind = document.get("fixture_type")
        if kind not in {"synthetic", "human_reviewed"}:
            raise ValueError("fixture_type must be synthetic or human_reviewed")
        rows, gold = document["records"], document["labels"]
        if not isinstance(gold, dict):
            raise ValueError("gold labels must be an object")
    else:
        with Path(input_file).open(encoding="utf-8") as source:
            rows = [json.loads(line) for line in source if line.strip()]
        gold, kind = None, "unlabeled_historical"
    return parse_articles(rows), gold, kind


def run_ablations(items, *, gold=None, kind="unlabeled_historical",
                  window_days=7, minimum_score=0.34):
    if kind == "synthetic" and gold is None:
        raise ValueError("synthetic fixture must carry labels")
    if gold is not None and kind not in {"synthetic", "human_reviewed"}:
        raise ValueError("gold labels require reviewed provenance")
    ids = [item.news_id for item in items]
    ground_truth = partition_from_gold(gold, ids) if gold is not None else None
    report = {
        "dataset_kind": kind,
        "gold_quality_valid_for_real_world": kind == "human_reviewed",
        "params": {"window_days": window_days, "minimum_score": minimum_score},
        "variants": {},
        "warnings": [
            "Coverage concentration is diagnostic, not measured accuracy.",
            "Preview event IDs are membership hashes and MUST NOT replace production event IDs.",
        ],
    }
    blocked = blocked_pair_ids(items, window_days=window_days)
    report["candidate_blocking"] = {
        "pairs": len(blocked),
        "gold_retrieval": pair_retrieval_metrics(ground_truth, blocked, ids)
        if ground_truth is not None else None,
    }
    for variant in ("legacy", "connected", "constrained"):
        clusters, edges = cluster(
            items, variant=variant, window_days=window_days,
            minimum_score=minimum_score,
        )
        entry = {
            "diagnostics": partition_diagnostics(clusters, items),
            "qualified_pair_edges": len(edges),
            "preview_events": [
                {"preview_id": preview_event_id(c), "news_count": len(c),
                 "members": list(c)}
                for c in clusters if len(c) >= 2
            ][:15],
        }
        if ground_truth is not None:
            entry["edge_retrieval"] = (pair_retrieval_metrics(
                ground_truth, ((e.left, e.right) for e in edges), ids
            ) if variant != "legacy" else None)
            entry["gold_pairwise"] = pairwise_metrics(ground_truth, clusters, ids)
            entry["gold_bcubed"] = bcubed_metrics(ground_truth, clusters, ids)
        else:
            entry["edge_retrieval"] = None
            entry["gold_pairwise"] = None
            entry["gold_bcubed"] = None
        report["variants"][variant] = entry
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="Historical JSONL, without gold labels")
    source.add_argument("--fixture", type=Path, help="Synthetic or reviewed records with labels")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--minimum-score", type=float, default=0.34)
    parser.add_argument("--output", type=Path, help="Optional full JSON report file")
    args = parser.parse_args()
    items, gold, kind = load_inputs(
        input_file=args.input or (ROOT / "data" / "news_items.jsonl") if not args.fixture else None,
        fixture=args.fixture,
    )
    report = run_ablations(
        items, gold=gold, kind=kind,
        window_days=args.window_days, minimum_score=args.minimum_score,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    summary = {
        "dataset_kind": report["dataset_kind"], "items": len(items),
        "candidate_blocking": report["candidate_blocking"],
        "variants": {
            name: {
                "diagnostics": entry["diagnostics"],
                "gold_pairwise": entry["gold_pairwise"],
                "gold_bcubed": entry["gold_bcubed"],
                "edge_retrieval": entry["edge_retrieval"],
            } for name, entry in report["variants"].items()
        },
        "note": "No event data was written to SQLite or data/*.json",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
