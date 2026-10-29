#!/usr/bin/env python3
"""Create a balanced UNLABELED pair-review queue. No generated labels are truth.

Pools represent sampling strata, not inferred SAME/DIFFERENT decisions.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.event_clustering_v3 import candidate_edges, parse_articles


def make_queue(items, *, limit=90, seed=20261029, raw_by_id=None, window_days=7):
    if limit <= 0 or window_days < 0:
        raise ValueError("invalid annotation sampling parameters")
    raw_by_id = raw_by_id or {}
    lookup = {a.news_id: a for a in items}
    scored = candidate_edges(items, window_days=window_days)
    positives = [tuple(sorted((e.left, e.right))) for e in scored]
    scored_lookup = {(e.left, e.right): e for e in scored}
    known = set(positives)
    topical = []
    controls = []

    # Small-corpus baseline; for multiyear data replace with indexed sampling.
    ordered = sorted(items, key=lambda a: (a.day, a.news_id))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if (b.day - a.day).days > window_days:
                break
            pair = tuple(sorted((a.news_id, b.news_id)))
            if pair in known:
                continue
            if a.topics & b.topics or a.people & b.people or a.organizations & b.organizations:
                topical.append(pair)
            else:
                controls.append(pair)

    rng = random.Random(seed)
    rng.shuffle(positives)
    rng.shuffle(topical)
    rng.shuffle(controls)
    pool_map = {
        "model_positive": positives,
        "topical_unmatched": topical,
        "random_control": controls,
    }
    selected = []
    seen = set()
    # Balanced as far as the observed pools allow; unspecified pairs remain
    # unreviewed rather than being treated as negative.
    quotas = {
        "model_positive": limit // 3,
        "topical_unmatched": limit // 3,
        "random_control": limit - 2 * (limit // 3),
    }
    for kind in pool_map:
        for pair in pool_map[kind][:quotas[kind]]:
            seen.add(pair)
            selected.append((kind, pair))
    for kind in pool_map:
        for pair in pool_map[kind]:
            if len(selected) >= limit:
                break
            if pair not in seen:
                selected.append((kind, pair))
                seen.add(pair)
    rows = []
    for kind, (left_id, right_id) in selected:
        a, b = lookup[left_id], lookup[right_id]
        edge = scored_lookup.get((left_id, right_id))
        left_raw, right_raw = raw_by_id.get(left_id, {}), raw_by_id.get(right_id, {})
        rows.append({
            "left_id": left_id, "right_id": right_id,
            "sampling_stratum": kind,
            "source": {
                "left_title": a.title, "right_title": b.title,
                "left_date": a.day.isoformat(), "right_date": b.day.isoformat(),
                "left_url": left_raw.get("url"), "right_url": right_raw.get("url"),
                "left_excerpt": left_raw.get("excerpt") or left_raw.get("summary"),
                "right_excerpt": right_raw.get("excerpt") or right_raw.get("summary"),
            },
            "evidence": {
                "matched_pair_score": edge.score if edge else None,
                "shared_topics": sorted(a.topics & b.topics),
                "shared_people": sorted(a.people & b.people),
                "shared_organizations": sorted(a.organizations & b.organizations),
            },
            "reviewer_1": {"id": None, "label": None, "evidence": None},
            "reviewer_2": {"id": None, "label": None, "evidence": None},
            "adjudication": {"label": None, "reviewer": None, "note": None},
        })
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ROOT / "data" / "news_items.jsonl")
    p.add_argument("--output", type=Path, required=True,
                   help="Write outside tracked data; all annotation labels begin null")
    p.add_argument("--limit", type=int, default=90)
    p.add_argument("--seed", type=int, default=20261029)
    p.add_argument("--start", type=date.fromisoformat, help="First broadcast date YYYY-MM-DD")
    p.add_argument("--end", type=date.fromisoformat, help="Last broadcast date YYYY-MM-DD")
    args = p.parse_args()
    if args.output.resolve() == args.input.resolve():
        p.error("refusing to overwrite input data")
    with args.input.open(encoding="utf-8") as source:
        raw = [json.loads(line) for line in source if line.strip()]
    items = parse_articles(raw)
    items = [a for a in items if (not args.start or a.day >= args.start)
             and (not args.end or a.day <= args.end)]
    raw_by_id = {row["news_id"]: row for row in raw}
    queue = make_queue(items, limit=args.limit, seed=args.seed, raw_by_id=raw_by_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in queue:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(args.output)
    print(f"Wrote {len(queue)} UNLABELED, stratified review tasks to {args.output}")
    print(json.dumps({
        kind: sum(x["sampling_stratum"] == kind for x in queue)
        for kind in ("model_positive", "topical_unmatched", "random_control")
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
