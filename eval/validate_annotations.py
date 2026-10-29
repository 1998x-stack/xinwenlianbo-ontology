#!/usr/bin/env python3
"""Validate double-blind annotations, disagreements and adjudications.

This validates pairwise review readiness; it DOES NOT silently turn
unlabeled pairs into negative labels or manufacture full event gold clusters.
"""

from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

LABELS = {"SAME_EVENT", "RELATED_NOT_SAME", "DIFFERENT_EVENT", "UNSURE"}
DEFINITIVE = LABELS - {"UNSURE"}


def validate_reviews(rows):
    seen = set()
    counts = Counter()
    reviewer1 = Counter()
    reviewer2 = Counter()
    for row in rows:
        left, right = row["left_id"], row["right_id"]
        if left == right:
            raise ValueError("a pair cannot reference the same article twice")
        key = tuple(sorted((left, right)))
        if key in seen:
            raise ValueError(f"duplicate review pair: {key}")
        seen.add(key)
        l, r = row["reviewer_1"], row["reviewer_2"]
        a, b = l.get("label"), r.get("label")
        for value in (a, b, row.get("adjudication", {}).get("label")):
            if value is not None and value not in LABELS:
                raise ValueError(f"unsupported annotation label: {value}")
        if a is None or b is None:
            counts["unreviewed"] += 1
            continue
        if not l.get("id") or not r.get("id") or l["id"] == r["id"]:
            raise ValueError("completed reviews require two distinct reviewer IDs")
        counts["double_reviewed"] += 1
        reviewer1[a] += 1
        reviewer2[b] += 1
        verdict = row.get("adjudication", {}).get("label")
        if a == b and a in DEFINITIVE:
            counts["agreed"] += 1
            counts["ready"] += 1
        elif verdict in DEFINITIVE and row.get("adjudication", {}).get("reviewer"):
            counts["adjudicated"] += 1
            counts["ready"] += 1
        else:
            counts["needs_adjudication"] += 1
    n = counts["double_reviewed"]
    observed_agreement = sum(
        row["reviewer_1"].get("label") == row["reviewer_2"].get("label")
        for row in rows
        if row["reviewer_1"].get("label") is not None
        and row["reviewer_2"].get("label") is not None
    ) / n if n else None
    expected_agreement = sum(
        reviewer1[label] * reviewer2[label] for label in LABELS
    ) / (n * n) if n else None
    kappa = (
        ((observed_agreement - expected_agreement) / (1 - expected_agreement))
        if n and expected_agreement < 1 else None
    )
    return {
        "total_pairs": len(rows), "unreviewed": counts["unreviewed"],
        "double_reviewed": n, "agreed_and_definitive": counts["agreed"],
        "adjudicated": counts["adjudicated"],
        "needs_adjudication": counts["needs_adjudication"],
        "ready_definitive_pairs": counts["ready"],
        "reviewer_agreement": round(observed_agreement, 6)
        if observed_agreement is not None else None,
        "cohens_kappa": round(kappa, 6) if kappa is not None else None,
        "note": "Reviewed pairs do not imply a fully annotated event partition.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="JSONL from make_annotation_queue.py")
    args = p.parse_args()
    with args.input.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    print(json.dumps(validate_reviews(rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
