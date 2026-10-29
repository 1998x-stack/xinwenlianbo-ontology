#!/usr/bin/env python3
"""Deterministic date-stratified small subset selection for exhaustive review.

Not statistically representative; review a separate, frozen test window before
claiming population metrics.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.event_clustering_v3 import parse_articles


def select(rows, *, count=12, start=None, end=None, seed=20261029):
    if count < 2:
        raise ValueError("at least two items needed")
    articles = [a for a in parse_articles(rows)
                if (start is None or a.day.isoformat() >= start)
                and (end is None or a.day.isoformat() <= end)]
    if len(articles) < count:
        raise ValueError("not enough items in selected date interval")
    by_day = defaultdict(list)
    for a in articles:
        by_day[a.day.isoformat()].append(a.news_id)
    rng = random.Random(seed)
    dates = sorted(by_day)
    for day in dates:
        rng.shuffle(by_day[day])
    choice = []
    while len(choice) < count:
        grew = False
        for day in dates:
            if by_day[day] and len(choice) < count:
                choice.append(by_day[day].pop())
                grew = True
        if not grew:
            break
    return sorted(choice)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--count", type=int, default=12)
    p.add_argument("--start", help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD")
    p.add_argument("--seed", type=int, default=20261029)
    args = p.parse_args()
    if args.input.resolve() == args.output.resolve():
        p.error("refusing to overwrite source")
    with args.input.open(encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    ids = select(rows, count=args.count, start=args.start, end=args.end,
                 seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".tmp")
    temp.write_text(json.dumps(ids, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({"items": len(ids), "selection": str(args.output),
                      "unlabeled": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
