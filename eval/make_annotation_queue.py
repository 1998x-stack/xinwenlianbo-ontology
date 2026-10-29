#!/usr/bin/env python3
"""Generate an unlabeled event-pair annotation queue from historical exports.

The output is a reviewer task list, not a gold standard. All judgments are null
until independently reviewed and adjudicated.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.event_clustering_v3 import candidate_edges, parse_articles


def make_queue(items, limit=80):
    if limit <= 0:
        raise ValueError("limit must be positive")
    lookup = {a.news_id: a for a in items}
    edges = candidate_edges(items)
    rows = []
    for edge in edges[:limit]:
        a, b = lookup[edge.left], lookup[edge.right]
        rows.append({
            "left_id": edge.left, "right_id": edge.right,
            "left_title": a.title, "right_title": b.title,
            "left_broadcast_date": a.day.isoformat(), "right_broadcast_date": b.day.isoformat(),
            "overlap_evidence": {
                "title_similarity": edge.title_similarity,
                "keyword_similarity": edge.keyword_similarity,
                "shared_people": list(edge.shared_people),
                "shared_organizations": list(edge.shared_organizations),
                "shared_topics": list(edge.shared_topics),
            },
            "review_label": None, "reviewer_id": None, "reviewed_at": None,
            "adjudicated_label": None,
            "annotation_note": None,
        })
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ROOT / "data" / "news_items.jsonl")
    p.add_argument("--output", type=Path, required=True,
                   help="Write outside the tracked data directory; labels start null")
    p.add_argument("--limit", type=int, default=80)
    args = p.parse_args()
    if args.output.resolve() == args.input.resolve():
        p.error("refusing to overwrite input data")
    with args.input.open(encoding="utf-8") as source:
        items = parse_articles([json.loads(line) for line in source if line.strip()])
    queue = make_queue(items, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".tmp")
    with temp.open("w", encoding="utf-8") as output:
        for row in queue:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    temp.replace(args.output)
    print(f"Wrote {len(queue)} UNLABELED review tasks to {args.output}")


if __name__ == "__main__":
    main()
