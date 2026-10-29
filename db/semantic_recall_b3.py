"""Experimental B3: semantic recall + event-centroid assignment (read-only).

Vectors are explicit, versioned input. Nothing downloads models, creates
production event IDs, modifies SQLite, or publishes graph data here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re

from db.event_clustering_v3 import Article, headline, grams, jaccard, GENERIC_HEADLINES

ACTION_TERMS = (
    "会见", "会谈", "访问", "签署", "发布", "启动", "发射", "落地",
    "开工", "竣工", "举行", "召开", "演习", "救援", "防汛", "抗洪",
    "通报", "审议", "批准", "宣布", "抵达", "离开", "返回",
    "建设", "检查", "调研", "试运行", "完成", "闭幕", "开幕",
)
# Priority on more specific verbs so generic "举行" cannot conflate meetings.
ACTION_SHADOW = {"举行", "召开", "宣布", "完成", "建设"}
LOCATION = re.compile(r"[\u4e00-\u9fff]{1,4}(?:省|市|县)")


@dataclass(frozen=True)
class SemanticPair:
    left: str
    right: str
    similarity: float
    lexical_similarity: float
    shared_people: tuple[str, ...]
    shared_organizations: tuple[str, ...]
    shared_actions: tuple[str, ...]


@dataclass(frozen=True)
class VectorManifest:
    model_id: str
    revision: str
    input_sha256: str
    text_template: str
    dimension: int


def input_sha256(path):
    """Hash exact input bytes, not silently transformed or re-ordered data."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize(vector):
    if not isinstance(vector, (list, tuple)) or not vector:
        raise ValueError("vector must be a non-empty numeric array")
    if any(isinstance(x, bool) or not isinstance(x, (int, float))
           or not math.isfinite(x) for x in vector):
        raise ValueError("non-finite or non-numeric vector")
    norm = math.sqrt(sum(float(x) * float(x) for x in vector))
    if norm <= 0:
        raise ValueError("zero-norm embedding")
    return tuple(float(x) / norm for x in vector)


def _validate_vectors(items, vectors):
    ids = {a.news_id for a in items}
    if not isinstance(vectors, dict) or set(vectors) != ids:
        missing = sorted(ids - set(vectors)) if isinstance(vectors, dict) else []
        raise ValueError(f"embedding IDs must exactly match articles, missing: {missing[:5]}")
    result = {}
    dim = None
    for nid in sorted(vectors):
        value = normalize(vectors[nid])
        if dim is None:
            dim = len(value)
        if len(value) != dim:
            raise ValueError("inconsistent embedding dimensions")
        result[nid] = value
    return result, (dim or 0)


def load_embeddings(path, items, *, source_path):
    """Require exact ID coverage and input-byte provenance before comparisons."""
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    if payload.get("format_version") != 1:
        raise ValueError("unsupported embeddings format")
    for field in ("model_id", "revision", "input_sha256", "text_template"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"embedding provenance field missing: {field}")
    digest = input_sha256(source_path)
    if digest != payload["input_sha256"]:
        raise ValueError("source input changed after embeddings were computed")
    values, dim = _validate_vectors(items, payload.get("vectors"))
    declared = payload.get("dimension")
    if isinstance(declared, bool) or declared != dim:
        raise ValueError("declared embedding dimension mismatch")
    manifest = VectorManifest(payload["model_id"], payload["revision"],
                              digest, payload["text_template"], dim)
    return manifest, values


def cosine(left, right):
    if len(left) != len(right):
        raise ValueError("incompatible embedding dimensions")
    return max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(left, right))))


def actions(title):
    title = headline(title)
    found = {term for term in ACTION_TERMS if term in title}
    specific = found - ACTION_SHADOW
    return frozenset(specific if specific else found)


def locations(title):
    return frozenset(LOCATION.findall(title))


def pair_compatible(a: Article, b: Article):
    """Conservative contradiction filters; an identity decision needs more evidence."""
    ta, tb = headline(a.title), headline(b.title)
    if ta in GENERIC_HEADLINES or tb in GENERIC_HEADLINES:
        return False
    # Explicit distinct organizations without a shared actor suggest
    # separately instantiated events, even if embedding vectors are similar.
    if a.organizations and b.organizations and not (a.organizations & b.organizations):
        if not (a.people & b.people):
            return False
    act_a, act_b = actions(a.title), actions(b.title)
    if act_a and act_b and not (act_a & act_b):
        return False
    geo_a, geo_b = locations(a.title), locations(b.title)
    if geo_a and geo_b and not (geo_a & geo_b):
        return False
    return True


def semantic_pairs(items, embeddings, *, window_days=7, top_k=8,
                   min_similarity=0.74):
    """Symmetric union of per-document top-k within a date window.

    Brute-force cosine is intentional for small experimental corpora.
    Benchmark/index it for multi-year datasets, never pretend this is ANN.
    """
    if window_days < 0 or top_k < 1 or not 0 <= min_similarity <= 1:
        raise ValueError("invalid semantic recall parameters")
    vectors, _ = _validate_vectors(items, embeddings)
    ordered = sorted(items, key=lambda a: (a.day, a.news_id))
    proposed = {}
    for a in ordered:
        neighbors = []
        for b in ordered:
            if a.news_id == b.news_id or abs((a.day - b.day).days) > window_days:
                continue
            if not pair_compatible(a, b):
                continue
            sim = cosine(vectors[a.news_id], vectors[b.news_id])
            if sim >= min_similarity:
                neighbors.append((sim, b.news_id))
        neighbors.sort(key=lambda x: (-x[0], x[1]))
        for sim, nid in neighbors[:top_k]:
            key = tuple(sorted((a.news_id, nid)))
            proposed[key] = max(proposed.get(key, -1.0), sim)
    lookup = {a.news_id: a for a in items}
    result = []
    for (left, right), sim in sorted(proposed.items(), key=lambda x: (-x[1], x[0])):
        a, b = lookup[left], lookup[right]
        result.append(SemanticPair(
            left, right, round(sim, 6), round(jaccard(grams(a.title), grams(b.title)), 6),
            tuple(sorted(a.people & b.people)),
            tuple(sorted(a.organizations & b.organizations)),
            tuple(sorted(actions(a.title) & actions(b.title))),
        ))
    return result


def _centroid(ids, embeddings):
    dim = len(embeddings[next(iter(ids))])
    return normalize([math.fsum(embeddings[nid][i] for nid in ids) for i in range(dim)])


def centroid_clusters(items, embeddings, *, candidate_pairs=None,
                      window_days=7, max_span_days=30,
                      min_member_similarity=0.70,
                      min_centroid_similarity=0.78):
    """Online, deterministic assignment to a candidate-supported event center.

    No cluster merge by transitive closure. A new article may attach only
    when a qualified candidate edge connects it to an existing member,
    every member is compatible, and all member/center vector gates pass.
    """
    if window_days < 0 or max_span_days < 0 or not 0 <= min_member_similarity <= 1 \
            or not 0 <= min_centroid_similarity <= 1:
        raise ValueError("invalid centroid parameters")
    vectors, _ = _validate_vectors(items, embeddings)
    pairs = {tuple(sorted(pair)) for pair in (candidate_pairs or [])}
    lookup = {a.news_id: a for a in items}
    groups = []
    for item in sorted(items, key=lambda a: (a.day, a.news_id)):
        possibilities = []
        for index, group in enumerate(groups):
            dates = [lookup[nid].day for nid in group] + [item.day]
            if (max(dates) - min(dates)).days > max_span_days:
                continue
            if not any(tuple(sorted((item.news_id, nid))) in pairs for nid in group):
                continue
            if not all(pair_compatible(item, lookup[nid]) for nid in group):
                continue
            # Do not impose the 7-day window on *all* historical members:
            # an event can last longer than a single news-pair candidate window.
            similarities = [cosine(vectors[item.news_id], vectors[nid]) for nid in group]
            if min(similarities) < min_member_similarity:
                continue
            centroid_similarity = cosine(vectors[item.news_id], _centroid(group, vectors))
            if centroid_similarity < min_centroid_similarity:
                continue
            possibilities.append((centroid_similarity, -len(group), index))
        if not possibilities:
            groups.append([item.news_id])
        else:
            _, _, index = max(possibilities)
            groups[index].append(item.news_id)
    return sorted((tuple(sorted(group)) for group in groups), key=lambda g: (g[0], len(g)))
