"""Partition validation and gold-set metrics for event clustering.

Metrics are valid only when gold labels were independently annotated. Synthetic
fixtures are useful for regression, not estimates of historical precision.
"""

from __future__ import annotations
from collections import Counter, defaultdict
from itertools import combinations


def label_partition(clusters, expected_ids):
    expected = set(expected_ids)
    if len(expected) != len(list(expected_ids)):
        raise ValueError("duplicate expected news IDs")
    membership = {}
    for idx, cluster in enumerate(clusters):
        if not cluster:
            raise ValueError("empty event cluster")
        for nid in cluster:
            if nid not in expected or nid in membership:
                raise ValueError(f"unknown or duplicated event membership: {nid}")
            membership[nid] = idx
    if set(membership) != expected:
        raise ValueError(f"missing event members: {sorted(expected - set(membership))[:5]}")
    return membership


def partition_from_gold(labels, expected_ids):
    expected = set(expected_ids)
    if set(labels) != expected:
        raise ValueError("gold annotations and input IDs must match exactly")
    groups = defaultdict(list)
    for nid, event in labels.items():
        if event is None or str(event).strip() == "":
            raise ValueError(f"invalid gold event label: {nid}")
        groups[str(event)].append(nid)
    return [tuple(sorted(v)) for _, v in sorted(groups.items())]


def pairwise_metrics(gold, predicted, expected_ids):
    ids = tuple(sorted(expected_ids))
    g = label_partition(gold, ids)
    p = label_partition(predicted, ids)
    tp = fp = fn = 0
    for left, right in combinations(ids, 2):
        same_gold, same_pred = g[left] == g[right], p[left] == p[right]
        if same_gold and same_pred:
            tp += 1
        elif same_pred:
            fp += 1
        elif same_gold:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else (1.0 if tp + fn == 0 else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 6), "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def bcubed_metrics(gold, predicted, expected_ids):
    ids = tuple(sorted(expected_ids))
    g = label_partition(gold, ids)
    p = label_partition(predicted, ids)
    if not ids:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    gold_groups = Counter(g.values())
    predicted_groups = Counter(p.values())
    intersections = Counter((g[nid], p[nid]) for nid in ids)
    precision = sum(intersections[(g[nid], p[nid])] / predicted_groups[p[nid]] for nid in ids) / len(ids)
    recall = sum(intersections[(g[nid], p[nid])] / gold_groups[g[nid]] for nid in ids) / len(ids)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6)}


def partition_diagnostics(clusters, articles):
    expected = [a.news_id for a in articles]
    label_partition(clusters, expected)
    sizes = [len(c) for c in clusters]
    days = {a.news_id: a.day for a in articles}
    spans = [(max(days[nid] for nid in c) - min(days[nid] for nid in c)).days for c in clusters]
    total = len(expected)
    return {
        "items": total,
        "clusters": len(clusters),
        "largest_cluster": max(sizes, default=0),
        "largest_share": round(max(sizes, default=0) / total, 6) if total else 0.0,
        "singletons": sum(s == 1 for s in sizes),
        "maximum_cluster_span_days": max(spans, default=0),
        "size_histogram": dict(sorted(Counter(sizes).items())),
    }



def pair_retrieval_metrics(gold, retrieved_pairs, expected_ids):
    """Recall and purity of explicitly retrieved pairs before clustering."""
    ids = tuple(sorted(expected_ids))
    labels = label_partition(gold, ids)
    valid = set(ids)
    pairs = set()
    for left, right in retrieved_pairs:
        if left not in valid or right not in valid or left == right:
            raise ValueError(f"invalid candidate pair: {left!r}, {right!r}")
        pairs.add(tuple(sorted((left, right))))
    gold_group_size = Counter(labels.values())
    positives = sum(count * (count - 1) // 2 for count in gold_group_size.values())
    tp = sum(labels[left] == labels[right] for left, right in pairs)
    false_positive = len(pairs) - tp
    false_negative = positives - tp
    precision = tp / len(pairs) if pairs else (1.0 if positives == 0 else 0.0)
    recall = tp / positives if positives else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "retrieved_pairs": len(pairs),
        "gold_positive_pairs": positives,
        "tp": tp, "fp": false_positive, "fn": false_negative,
        "precision": round(precision, 6), "recall": round(recall, 6),
        "f1": round(f1, 6),
    }
