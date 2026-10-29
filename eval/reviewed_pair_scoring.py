"""Score only adjudicated, explicitly labeled pairs; never invent negative gold."""

from __future__ import annotations

from collections import Counter

VALID = {"SAME_EVENT", "RELATED_NOT_SAME", "DIFFERENT_EVENT", "UNSURE"}


def resolved_label(row):
    one, two = row["reviewer_1"], row["reviewer_2"]
    a, b = one.get("label"), two.get("label")
    if a is None or b is None:
        return None
    if a not in VALID or b not in VALID:
        raise ValueError("unsupported reviewer label")
    if not one.get("id") or not two.get("id") or one.get("id") == two.get("id"):
        raise ValueError("two distinct reviewers are required")
    if a == b and a != "UNSURE":
        return a
    arbitration = row.get("adjudication", {})
    if arbitration.get("label") in VALID - {"UNSURE"} and arbitration.get("reviewer"):
        return arbitration["label"]
    return None


def membership_pairs(clusters):
    """Return exact same-event pair set, no transitive guess beyond clustering."""
    seen = set()
    output = set()
    for group in clusters:
        for nid in group:
            if nid in seen:
                raise ValueError(f"duplicate cluster membership: {nid}")
            seen.add(nid)
        ordered = sorted(group)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1:]:
                output.add((left, right))
    return output


def reviewed_pair_metrics(queue, predicted_pairs):
    """Metrics on *reviewed sample only*. Selection bias needs weighting later."""
    normalized = {tuple(sorted(p)) for p in predicted_pairs}
    counts = Counter()
    strata: dict[str, Counter] = {}
    seen = set()
    for row in queue:
        left, right = row["left_id"], row["right_id"]
        key = tuple(sorted((left, right)))
        if left == right or key in seen:
            raise ValueError(f"duplicate or self review pair: {key}")
        seen.add(key)
        label = resolved_label(row)
        if label is None:
            counts["unresolved"] += 1
            continue
        counts["resolved"] += 1
        stratum = row.get("sampling_stratum", "unspecified")
        bucket = strata.setdefault(stratum, Counter())
        positive = label == "SAME_EVENT"
        predicted = key in normalized
        cell = "tp" if positive and predicted else "fn" if positive else "fp" if predicted else "tn"
        counts[cell] += 1
        bucket[cell] += 1

    def measure(c):
        total = sum(c[x] for x in ("tp", "fp", "fn", "tn"))
        if total == 0:
            return {"n": 0, "precision": None, "recall": None, "f1": None,
                    "tp": 0, "fp": 0, "fn": 0, "tn": 0}
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if (
            precision is not None and recall is not None and precision + recall) else (
                0.0 if precision is not None and recall is not None else None
            )
        return {
            "n": total, "tp": tp, "fp": fp, "fn": fn, "tn": c["tn"],
            "precision": round(precision, 6) if precision is not None else None,
            "recall": round(recall, 6) if recall is not None else None,
            "f1": round(f1, 6) if f1 is not None else None,
        }

    return {
        "overall_reviewed_sample": measure(counts),
        "by_stratum": {key: measure(c) for key, c in sorted(strata.items())},
        "unresolved_pairs": counts["unresolved"],
        "warning": "Sampling is stratified/nonrandom; scores do not estimate population accuracy.",
    }
