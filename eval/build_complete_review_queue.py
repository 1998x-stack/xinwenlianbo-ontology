#!/usr/bin/env python3
"""Make an exhaustive, unbiased-for-the-selected-subset review queue.

All labels start null. These tasks require two actual independent reviewers.
"""
import argparse
from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.event_clustering_v3 import parse_articles


def complete_review_queue(rows, selected_ids):
    indexed = {row["news_id"]: row for row in rows}
    if len(selected_ids) < 2 or len(selected_ids) != len(set(selected_ids)):
        raise ValueError("selection needs >=2 unique IDs")
    if not set(selected_ids) <= indexed.keys():
        raise ValueError("selection contains unknown news IDs")
    queue = []
    for left, right in combinations(sorted(selected_ids), 2):
        a, b = indexed[left], indexed[right]
        queue.append({
            "left_id": left, "right_id": right,
            "sampling_stratum": "exhaustive_selected_subset",
            "source": {
                "left_title": a["title"],
                "right_title": b["title"],
                "left_date": a["broadcast_date"],
                "right_date": b["broadcast_date"],
                "left_url": a.get("url"),
                "right_url": b.get("url"),
                "left_excerpt": a.get("excerpt") or a.get("summary"),
                "right_excerpt": b.get("excerpt") or b.get("summary"),
            },
            "reviewer_1": {"id": None, "label": None, "evidence": None},
            "reviewer_2": {"id": None, "label": None, "evidence": None},
            "adjudication": {"label": None, "reviewer": None, "note": None},
        })
    return queue


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() in {args.input.resolve(), args.selection.resolve()}:
        p.error("refusing to overwrite input")
    with args.input.open(encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    parse_articles(rows)
    ids = json.loads(args.selection.read_text(encoding="utf-8"))
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        p.error("selection must be JSON array of news IDs")
    queue = complete_review_queue(rows, ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_name(args.output.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in queue:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(args.output)
    print(json.dumps({"articles": len(ids), "pairs": len(queue),
                      "status": "ALL_UNLABELED", "output": str(args.output)}))


if __name__ == "__main__":
    main()
