"""Deterministic, auditable, dependency-free event clustering experiments.

This module does not update the production SQLite tables. Event IDs here
identify preview clusters only; production event identity requires a registry.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from itertools import combinations
import re
from typing import Iterable

GENERIC_HEADLINES = frozenset((
    "国内联播快讯", "国际联播快讯", "联播快讯", "新闻联播",
))
TITLE_PREFIX = re.compile(r"^【[^】]{1,32}】")
NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


@dataclass(frozen=True)
class Article:
    news_id: str
    day: date
    title: str
    topics: frozenset[str]
    people: frozenset[str]
    organizations: frozenset[str]
    keywords: frozenset[str]


@dataclass(frozen=True)
class PairEvidence:
    left: str
    right: str
    score: float
    title_similarity: float
    keyword_similarity: float
    shared_topics: tuple[str, ...]
    shared_people: tuple[str, ...]
    shared_organizations: tuple[str, ...]
    shared_ngrams: tuple[str, ...]


def _names(items, key="name") -> frozenset[str]:
    if not isinstance(items, list):
        return frozenset()
    result = set()
    for value in items:
        name = value.get(key) if isinstance(value, dict) else value
        if isinstance(name, str) and name.strip():
            result.add(name.strip())
    return frozenset(result)


def parse_articles(rows: list[dict]) -> list[Article]:
    """Validate input instead of permitting silent omissions or invalid dates."""
    output = []
    ids = set()
    for row in rows:
        nid = row["news_id"]
        if not isinstance(nid, str) or not nid or nid in ids:
            raise ValueError(f"Missing or duplicate news_id: {nid!r}")
        ids.add(nid)
        d = date.fromisoformat(row["broadcast_date"])
        if not isinstance(row.get("title"), str):
            raise ValueError(f"Missing title for {nid}")
        topics = _names(row.get("topics", []))
        people = _names(row.get("people", []), "name_chinese")
        organizations = _names(row.get("organizations", []))
        keywords = _names(row.get("keywords", []))
        output.append(Article(nid, d, row["title"], topics, people, organizations, keywords))
    return sorted(output, key=lambda x: (x.day, x.news_id))


def headline(title: str) -> str:
    return NON_WORD.sub("", TITLE_PREFIX.sub("", title).strip()).lower()


def grams(title: str) -> frozenset[str]:
    normalized = headline(title)
    if normalized in GENERIC_HEADLINES or len(normalized) < 4:
        return frozenset()
    return frozenset(normalized[i:i + 2] for i in range(len(normalized) - 1))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    aa, bb = set(a), set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _components(items: list[Article], edges: Iterable[tuple[str, str]]) -> list[tuple[str, ...]]:
    parent = {item.news_id: item.news_id for item in items}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for left, right in sorted(edges):
        lroot, rroot = root(left), root(right)
        if lroot != rroot:
            parent[max(lroot, rroot)] = min(lroot, rroot)
    groups: dict[str, list[str]] = defaultdict(list)
    for nid in sorted(parent):
        groups[root(nid)].append(nid)
    return sorted((tuple(group) for group in groups.values()), key=lambda g: (g[0], len(g)))


def legacy_clusters(items: list[Article], *, window_days: int = 7) -> list[tuple[str, ...]]:
    """Replicate the old top-three-topic exclusion + connected-components baseline.

    This uses the actual per-document topic frequency rather than cached counters.
    """
    freq = Counter(topic for a in items for topic in a.topics)
    excluded = {name for name, _ in sorted(freq.items(), key=lambda p: (-p[1], p[0]))[:3]}
    by_topic: dict[str, list[Article]] = defaultdict(list)
    for item in items:
        for topic in item.topics - excluded:
            by_topic[topic].append(item)
    links = set()
    for group in by_topic.values():
        group.sort(key=lambda a: (a.day, a.news_id))
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                if (right.day - left.day).days > window_days:
                    break
                links.add(tuple(sorted((left.news_id, right.news_id))))
    return _components(items, links)


def _candidate_pairs(items: list[Article], *, window_days: int = 7):
    """Indexed blocking: only compare items sharing an uncommon anchor."""
    n = len(items)
    topic_freq = Counter(t for item in items for t in item.topics)
    person_freq = Counter(t for item in items for t in item.people)
    org_freq = Counter(t for item in items for t in item.organizations)
    gram_freq = Counter(t for item in items for t in grams(item.title))
    # Omit dominant topics and high-frequency headline fragments/actors.
    generic_topics = {k for k, _ in sorted(topic_freq.items(), key=lambda p: (-p[1], p[0]))[:3]}
    index: dict[tuple[str, str], list[Article]] = defaultdict(list)
    for item in items:
        for t in item.topics - generic_topics:
            if topic_freq[t] <= max(2, n // 5):
                index[("topic", t)].append(item)
        for p in item.people:
            if person_freq[p] <= max(2, n // 10):
                index[("person", p)].append(item)
        for o in item.organizations:
            if org_freq[o] <= max(2, n // 10):
                index[("org", o)].append(item)
        for g in grams(item.title):
            if gram_freq[g] <= max(2, n // 12):
                index[("gram", g)].append(item)
    pairs: set[tuple[str, str]] = set()
    for block in index.values():
        if len(block) > 150:  # guard against accidental large posting lists
            continue
        block.sort(key=lambda a: (a.day, a.news_id))
        for i, left in enumerate(block):
            for right in block[i + 1:]:
                if (right.day - left.day).days > window_days:
                    break
                pairs.add(tuple(sorted((left.news_id, right.news_id))))
    return pairs, generic_topics




def blocked_pair_ids(items: list[Article], *, window_days: int = 7) -> set[tuple[str, str]]:
    """Inspect candidate-blocking recall separately from pairwise decisions."""
    if window_days < 0:
        raise ValueError("window_days must be nonnegative")
    pairs, _ = _candidate_pairs(items, window_days=window_days)
    return pairs

def candidate_edges(
    items: list[Article],
    *,
    window_days: int = 7,
    minimum_score: float = 0.34,
) -> list[PairEvidence]:
    """Generate scored edges; no shared broad topic or famous actor alone is enough."""
    if window_days < 0 or not 0 <= minimum_score <= 1:
        raise ValueError("invalid clustering parameters")
    lookup = {a.news_id: a for a in items}
    candidates, generic_topics = _candidate_pairs(items, window_days=window_days)
    output = []
    for left_id, right_id in sorted(candidates):
        left, right = lookup[left_id], lookup[right_id]
        if headline(left.title) in GENERIC_HEADLINES or headline(right.title) in GENERIC_HEADLINES:
            continue
        shared_topics = tuple(sorted((left.topics & right.topics) - generic_topics))
        shared_people = tuple(sorted(left.people & right.people))
        shared_orgs = tuple(sorted(left.organizations & right.organizations))
        # Conservative anti-merge rule: mutually exclusive named organizations
        # need independent actor evidence, not just a generic common topic.
        if (left.organizations and right.organizations
                and not shared_orgs and not shared_people):
            continue
        overlap = grams(left.title) & grams(right.title)
        lex = jaccard(grams(left.title), grams(right.title))
        kw = jaccard(left.keywords, right.keywords)
        actor = jaccard(left.people, right.people)
        org = jaccard(left.organizations, right.organizations)
        score = 0.60 * lex + 0.18 * kw + 0.12 * actor + 0.07 * org + (0.03 if shared_topics else 0.0)
        anchored = bool(shared_topics or shared_people or shared_orgs)
        # A rare shared gram and a topic alone are not enough; require lexical
        # agreement. Shared people alone do not mean the same event.
        if not anchored or not (lex >= 0.34 or (lex >= 0.20 and kw >= 0.25)):
            continue
        if score < minimum_score:
            continue
        output.append(PairEvidence(
            left_id, right_id, round(score, 6), round(lex, 6), round(kw, 6),
            shared_topics, shared_people, shared_orgs, tuple(sorted(overlap))[:12],
        ))
    return sorted(output, key=lambda e: (-e.score, e.left, e.right))


def constrained_clusters(
    items: list[Article],
    edges: list[PairEvidence],
    *,
    max_span_days: int = 30,
    min_cross_edge_fraction: float = 1.0,
) -> list[tuple[str, ...]]:
    """Complete-link by default: each new cross-pair must be a qualified edge.

    Lower cross-edge fractions are ablations, not a production default.
    No arbitrary maximum cluster-size cap masks giant-component failures.
    """
    if max_span_days < 0 or not 0 < min_cross_edge_fraction <= 1:
        raise ValueError("invalid cluster constraints")
    indexed = {a.news_id: a for a in items}
    clusters: dict[str, set[str]] = {nid: {nid} for nid in indexed}
    membership = {nid: nid for nid in indexed}
    good_edges = {(e.left, e.right) for e in edges}
    for edge in edges:
        la, rb = membership[edge.left], membership[edge.right]
        if la == rb:
            continue
        a, b = clusters[la], clusters[rb]
        dates = [indexed[nid].day for nid in a | b]
        if (max(dates) - min(dates)).days > max_span_days:
            continue
        required = len(a) * len(b)
        observed = sum(tuple(sorted((left, right))) in good_edges for left in a for right in b)
        if observed / required < min_cross_edge_fraction:
            continue
        keep, discard = min(la, rb), max(la, rb)
        clusters[keep] = a | b
        del clusters[discard]
        for nid in clusters[keep]:
            membership[nid] = keep
    return sorted((tuple(sorted(group)) for group in clusters.values()), key=lambda g: (g[0], len(g)))


def cluster(
    items: list[Article],
    *,
    variant: str = "constrained",
    minimum_score: float = 0.34,
    window_days: int = 7,
) -> tuple[list[tuple[str, ...]], list[PairEvidence]]:
    """Variant B0 is legacy, B1 is candidate-connected, B2 is constrained."""
    if variant == "legacy":
        return legacy_clusters(items, window_days=window_days), []
    edges = candidate_edges(items, window_days=window_days, minimum_score=minimum_score)
    if variant == "connected":
        return _components(items, ((e.left, e.right) for e in edges)), edges
    if variant == "constrained":
        return constrained_clusters(items, edges), edges
    raise ValueError(f"unknown event algorithm: {variant}")


def preview_event_id(members: Iterable[str]) -> str:
    """Ephemeral preview ID, not a stable real-world event identifier."""
    return "preview-" + sha256("|".join(sorted(members)).encode()).hexdigest()[:16]
