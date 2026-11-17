#!/usr/bin/env python3
"""Promote independently reviewed pair annotations to a SMALL, COMPLETE gold fixture.

No automatic labels. Require complete within-subset pair coverage OR proof of
same-event transitive closure plus explicit negative cross-group judgments.
Reject unresolved, inconsistent, or non-evidence-backed annotations.

This does not populate gold for the full historical dataset.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import date
from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.event_clustering_v3 import parse_articles
from db.semantic_recall_b3 import input_sha256
from eval.reviewed_pair_scoring import resolved_label

NEGATIVE = {"DIFFERENT_EVENT", "RELATED_NOT_SAME"}


def build_gold(records, queue, selected_ids, *, source_sha, guideline_version):
    """Construct an *exhaustively verified* event partition for a selected subset."""
    if not guideline_version or not isinstance(guideline_version, str):
        raise ValueError("annotation guideline version is required")
    if not source_sha or len(source_sha) != 64:
        raise ValueError("source SHA256 is required")
    indexed = {a["news_id"]: a for a in records}
    selected = set(selected_ids)
    if len(selected) < 2 or not selected <= indexed.keys():
        raise ValueError("selected IDs must be at least two distinct source articles")
    if len(selected) != len(selected_ids):
        raise ValueError("duplicate selected article IDs")
    judgments = {}
    reviewers = set()
    for row in queue:
        key = tuple(sorted((row["left_id"], row["right_id"])))
        if key[0] == key[1]:
            raise ValueError("self-referential review pair")
        if not set(key) <= selected:
            continue
        if key in judgments:
            raise ValueError("duplicate reviewed pair")
        verdict = resolved_label(row)
        if verdict is None:
            raise ValueError(f"pair not conclusively reviewed: {key}")
        source = row.get("source", {})
        # Exact title/date fields are required so review decisions reference
        # the immutable source snapshot rather than only inferred tags.
        for side, nid in zip(("left", "right"), (row["left_id"], row["right_id"])):
            title_key, day_key = f"{side}_title", f"{side}_date"
            if source.get(title_key) != indexed[nid]["title"] or (
                source.get(day_key) != indexed[nid]["broadcast_date"]
            ):
                raise ValueError(f"review source snapshot mismatch: {nid}")
        # A decision without explicit source-grounded evidence is not gold.
        # Evidence may be a verified short quotation, URL or source locator;
        # it is never populated automatically by a language model.
        for reviewer_key in ("reviewer_1", "reviewer_2"):
            evidence = row[reviewer_key].get("evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f"reviewer evidence missing for pair: {key}")
        if (row["reviewer_1"].get("label") != row["reviewer_2"].get("label")
                and not row.get("adjudication", {}).get("note")):
            raise ValueError(f"adjudication justification missing for pair: {key}")
        reviewers.add(row["reviewer_1"]["id"])
        reviewers.add(row["reviewer_2"]["id"])
        judgments[key] = verdict

    expected_pairs = {tuple(sorted(p)) for p in combinations(sorted(selected), 2)}
    if set(judgments) != expected_pairs:
        missing = sorted(expected_pairs - set(judgments))
        raise ValueError(f"gold subset requires exhaustive pair review: {len(missing)} missing; first {missing[:3]}")
    parent = {nid: nid for nid in selected}

    def root(nid):
        while parent[nid] != nid:
            parent[nid] = parent[parent[nid]]
            nid = parent[nid]
        return nid

    for (left, right), label in judgments.items():
        if label == "SAME_EVENT":
            a, b = root(left), root(right)
            parent[max(a, b)] = min(a, b)

    # Positive transitive closure is validated against EVERY explicit judgment.
    for (left, right), label in judgments.items():
        same = root(left) == root(right)
        if same != (label == "SAME_EVENT"):
            raise ValueError(f"contradictory same-event transitivity: {left}, {right}")
        if not same and label not in NEGATIVE:
            raise ValueError("unclassified negative event relation")

    groups = defaultdict(list)
    for nid in selected:
        groups[root(nid)].append(nid)
    labels = {}
    for _, members in sorted(groups.items()):
        # Fixture-specific partition labels are NOT persistent event UUIDs.
        group_id = "reviewed-" + min(members)
        for nid in members:
            labels[nid] = group_id
    subset = [indexed[nid] for nid in sorted(selected)]
    parse_articles(subset)
    return {
        "fixture_type": "human_reviewed",
        "annotation_protocol": "exhaustive_pairwise_two_reviewers_v1",
        "guideline_version": guideline_version,
        "source_input_sha256": source_sha,
        "reviewer_count": len(reviewers),
        "reviewed_pairs": len(expected_pairs),
        "records": subset,
        "labels": labels,
        "note": "Reviewed subset only; do not extrapolate F1 to all broadcasts.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="Exact source JSONL")
    p.add_argument("--reviews", type=Path, required=True, help="Double-reviewed pair JSONL")
    p.add_argument("--selection", type=Path, required=True, help="JSON array of chosen news IDs")
    p.add_argument("--guideline-version", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() in {args.input.resolve(), args.reviews.resolve(), args.selection.resolve()}:
        p.error("refusing to overwrite any input")
    with args.input.open(encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    with args.reviews.open(encoding="utf-8") as fh:
        reviews = [json.loads(line) for line in fh if line.strip()]
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if not isinstance(selection, list) or not all(isinstance(nid, str) for nid in selection):
        p.error("selection must be a JSON array of news IDs")
    fixture = build_gold(
        records, reviews, selection,
        source_sha=input_sha256(args.input), guideline_version=args.guideline_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".tmp")
    temp.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({
        "source": "two-reviewer verified subset", "articles": len(selection),
        "reviewed_pairs": fixture["reviewed_pairs"], "status": "human_reviewed",
        "output": str(args.output)
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
