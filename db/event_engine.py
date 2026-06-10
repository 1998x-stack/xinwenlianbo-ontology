"""Event detection engine for xinwenlianbo ontology.
Clusters news items into NewsEvents by topic similarity + temporal proximity."""

import hashlib, sqlite3, json, time, threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from ai_client import chat


def _make_event_id(news_ids):
    """Stable event_id from sorted news_ids — no AI text in hash."""
    sorted_ids = sorted(news_ids)
    raw = ",".join(sorted_ids)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _compute_topic_vector(conn, news_id):
    """Get topic_id set for a news item as its vector representation."""
    rows = conn.execute(
        "SELECT topic_id FROM news_topic WHERE news_id = ?", (news_id,)
    ).fetchall()
    return set(r["topic_id"] for r in rows)


def _days_between(d1, d2):
    """Calculate days between two date strings (YYYY-MM-DD)."""
    from datetime import datetime
    dt1 = datetime.strptime(d1, "%Y-%m-%d")
    dt2 = datetime.strptime(d2, "%Y-%m-%d")
    return (dt2 - dt1).days


def detect_events(conn, time_window_days=7, min_items=2):
    """Cluster news items into events by topic overlap + date proximity.

    Algorithm: For each news item, find all items within time_window_days
    that share at least 1 topic. Group connected components as events.
    Returns list of (event_name_hint, [news_ids]) tuples.
    """
    rows = conn.execute("""
        SELECT n.news_id, n.broadcast_date, n.title
        FROM news_item n
        ORDER BY n.broadcast_date
    """).fetchall()

    topic_vectors = {}
    for r in rows:
        topic_vectors[r["news_id"]] = _compute_topic_vector(conn, r["news_id"])

    date_map = {r["news_id"]: r["broadcast_date"] for r in rows}
    adjacency = defaultdict(set)

    for i, r1 in enumerate(rows):
        d1 = date_map[r1["news_id"]]
        v1 = topic_vectors.get(r1["news_id"], set())
        if not v1:
            continue
        for r2 in rows[i+1:]:
            d2 = date_map[r2["news_id"]]
            if abs(_days_between(d1, d2)) > time_window_days:
                continue
            v2 = topic_vectors.get(r2["news_id"], set())
            if v1 & v2:
                adjacency[r1["news_id"]].add(r2["news_id"])
                adjacency[r2["news_id"]].add(r1["news_id"])

    visited = set()
    events = []

    for nid in topic_vectors:
        if nid in visited:
            continue
        component = []
        queue = [nid]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(component) >= min_items:
            events.append(component)

    result = []
    for component in events:
        topic_counts = defaultdict(int)
        for nid in component:
            for t in topic_vectors.get(nid, set()):
                topic_counts[t] += 1
        top_topic = max(topic_counts, key=topic_counts.get) if topic_counts else "综合"
        topic_name_row = conn.execute(
            "SELECT name FROM topic WHERE topic_id=?", (top_topic,)
        ).fetchone()
        topic_name = topic_name_row["name"] if topic_name_row else top_topic
        dates = sorted(set(
            conn.execute("SELECT broadcast_date FROM news_item WHERE news_id=?", (nid,)).fetchone()["broadcast_date"]
            for nid in component
        ))
        name_hint = f"{topic_name}_{dates[0]}_{len(component)}条"
        result.append((name_hint, component))

    return result


def classify_event_type(conn, event_id):
    """Classify event type based on dominant topic category."""
    rows = conn.execute("""
        SELECT t.category FROM topic t
        JOIN news_topic nt ON t.topic_id = nt.topic_id
        JOIN news_event_link nel ON nt.news_id = nel.news_id
        WHERE nel.event_id = ?
    """, (event_id,)).fetchall()

    cat_counts = defaultdict(int)
    for r in rows:
        cat = (r["category"] or "").lower()
        cat_counts[cat] += 1

    if not cat_counts:
        return "political"

    type_map = {
        "economy": "economic", "politics": "political", "military": "military",
        "technology": "technological", "culture": "social", "environment": "environmental",
    }
    top_cat = max(cat_counts, key=cat_counts.get)
    return type_map.get(top_cat, "political")


def compute_heat_score(conn, event_id):
    """Calculate heat score: frequency*0.4 + recency*0.3 + acceleration*0.2 + actor_importance*0.1"""
    rows = conn.execute("""
        SELECT n.broadcast_date FROM news_item n
        JOIN news_event_link nel ON n.news_id = nel.news_id
        WHERE nel.event_id = ?
        ORDER BY n.broadcast_date
    """, (event_id,)).fetchall()

    if not rows:
        return 0.0

    dates = [r["broadcast_date"] for r in rows]
    n = len(dates)
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    frequency = min(n / 30.0, 1.0) * 100
    latest = dates[-1]
    days_since = _days_between(latest, today)
    recency = max(0, 100 - days_since * (100 / 30))

    recent = sum(1 for d in dates if _days_between(d, today) <= 7)
    earlier = sum(1 for d in dates if 7 < _days_between(d, today) <= 14)
    if earlier > 0:
        acceleration = min((recent / earlier) * 50, 100)
    else:
        acceleration = 50 if recent > 0 else 0

    actor_count = conn.execute("""
        SELECT COUNT(DISTINCT ep.person_id) as c FROM event_person ep
        WHERE ep.event_id = ?
    """, (event_id,)).fetchone()["c"]
    actor_importance = min(actor_count / 10.0, 1.0) * 100

    return round(frequency * 0.4 + recency * 0.3 + acceleration * 0.2 + actor_importance * 0.1, 1)


def compute_importance(heat_score):
    """Map heat score to importance level."""
    if heat_score >= 70: return "critical"
    elif heat_score >= 50: return "major"
    elif heat_score >= 30: return "notable"
    return "routine"


def compute_status(conn, event_id):
    """Determine lifecycle status based on coverage frequency trend."""
    rows = conn.execute("""
        SELECT n.broadcast_date FROM news_item n
        JOIN news_event_link nel ON n.news_id = nel.news_id
        WHERE nel.event_id = ?
        ORDER BY n.broadcast_date
    """, (event_id,)).fetchall()

    if not rows:
        return "archived"

    dates = [r["broadcast_date"] for r in rows]
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    days_since_last = _days_between(dates[-1], today)

    if days_since_last > 30: return "archived"
    if days_since_last > 7: return "resolved"

    recent_7 = sum(1 for d in dates if _days_between(d, today) <= 7)
    prev_7 = sum(1 for d in dates if 7 < _days_between(d, today) <= 14)

    if recent_7 == 0: return "declining"
    if recent_7 > prev_7 * 1.5: return "developing" if len(dates) > 3 else "emerging"
    if recent_7 >= prev_7 * 0.8: return "peak"
    if recent_7 < prev_7 * 0.5: return "declining"
    return "developing"
