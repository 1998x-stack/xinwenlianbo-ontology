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
    # Exclude super-connector topics (top N by frequency) from adjacency
    top_topics = conn.execute(
        "SELECT topic_id FROM topic ORDER BY article_count DESC LIMIT 3"
    ).fetchall()
    excluded = set(r["topic_id"] for r in top_topics)

    rows = conn.execute("""
        SELECT n.news_id, n.broadcast_date, n.title
        FROM news_item n
        ORDER BY n.broadcast_date
    """).fetchall()

    topic_vectors = {}
    for r in rows:
        full = _compute_topic_vector(conn, r["news_id"])
        topic_vectors[r["news_id"]] = full - excluded  # only specific topics

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
            if v1 & v2:  # share at least 1 specific topic
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


# ── AI-powered event synthesis ──────────────────────────────────────

EVENT_SYSTEM_PROMPT = """\
You are a senior news analyst specializing in Chinese current affairs.
Given a collection of news items from 《新闻联播》 that are all about the same event,
synthesize them into a coherent event profile.

Always respond in Chinese. Return ONLY valid JSON, no markdown fences."""


def generate_event_profile(conn, event_id):
    """AI-generated event name, summary, and type classification."""
    rows = conn.execute("""
        SELECT n.title, n.summary, n.broadcast_date
        FROM news_item n
        JOIN news_event_link nel ON n.news_id = nel.news_id
        WHERE nel.event_id = ?
        ORDER BY n.broadcast_date
    """, (event_id,)).fetchall()

    if not rows:
        return None

    items_text = []
    for r in rows:
        summary = r["summary"] or r["title"]
        items_text.append(f"[{r['broadcast_date']}] {r['title']}\n  {summary[:200]}")

    prompt = f"""Analyze these related news items from 《新闻联播》 and synthesize an event profile:

{chr(10).join(items_text)}

Return JSON:
{{
  "name": "事件名称（如：习近平2026年朝鲜国事访问，20字以内）",
  "type": "political|economic|military|diplomatic|social|technological|environmental",
  "summary": "3-5句事件综述（150-300字），涵盖起因、发展、关键节点、当前状态",
  "importance": "routine|notable|major|critical"
}}"""

    result_text = chat(prompt, EVENT_SYSTEM_PROMPT, temperature=0.3, max_tokens=1500)
    if not result_text:
        return None

    try:
        import json
        text = result_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        return json.loads(text)
    except json.JSONDecodeError:
        return {"name": f"事件_{event_id[:8]}", "type": "political", "summary": result_text[:300], "importance": "notable"}


def generate_event_report(conn, event_id):
    """AI-generated detailed event report: background, timeline, actors, outlook."""
    rows = conn.execute("""
        SELECT n.title, n.summary, n.full_text, n.broadcast_date
        FROM news_item n
        JOIN news_event_link nel ON n.news_id = nel.news_id
        WHERE nel.event_id = ?
        ORDER BY n.broadcast_date
    """, (event_id,)).fetchall()

    if not rows:
        return "No items linked to this event."

    event = conn.execute("SELECT * FROM news_event WHERE event_id=?", (event_id,)).fetchone()
    if not event:
        return "Event not found."

    persons = conn.execute("""
        SELECT p.name_chinese, ep.role FROM person p
        JOIN event_person ep ON p.person_id = ep.person_id
        WHERE ep.event_id = ? ORDER BY ep.role
    """, (event_id,)).fetchall()
    orgs = conn.execute("""
        SELECT o.name, eo.role FROM organization o
        JOIN event_organization eo ON o.org_id = eo.org_id
        WHERE eo.event_id = ? ORDER BY eo.role
    """, (event_id,)).fetchall()

    timeline = []
    for r in rows:
        preview = (r["summary"] or r["full_text"] or "")[:300]
        timeline.append(f"[{r['broadcast_date']}] {r['title']}\n  {preview}")

    prompt = f"""Generate a comprehensive event analysis report for this 《新闻联播》 event:

Event: {event['name']}
Type: {event['type']}
Importance: {event['importance']}
Status: {event['status']}
Dates: {event['first_date']} to {event['last_date']}

Key Actors:
{chr(10).join(f'- {p["name_chinese"]} ({p["role"]})' for p in persons[:10])}

Organizations:
{chr(10).join(f'- {o["name"]} ({o["role"]})' for o in orgs[:10])}

Timeline:
{chr(10).join(timeline)}

Write a 4-5 paragraph Chinese analysis covering:
1. Event background and context
2. Key developments and turning points
3. Major actors and their roles
4. Current status and future outlook
5. Policy implications (if applicable)

Be specific and cite dates. Use formal analytical language."""

    return chat(prompt, EVENT_SYSTEM_PROMPT, max_tokens=2000) or "Report generation failed."


def find_related_events(conn, event_id, max_related=5):
    """Find events that share persons with the given event."""
    rows = conn.execute("""
        SELECT e.event_id, e.name, COUNT(*) as shared
        FROM news_event e
        JOIN event_person ep ON e.event_id = ep.event_id
        WHERE ep.person_id IN (SELECT person_id FROM event_person WHERE event_id = ?)
          AND e.event_id != ?
        GROUP BY e.event_id ORDER BY shared DESC LIMIT ?
    """, (event_id, event_id, max_related)).fetchall()
    related = []
    for r in rows:
        e1 = conn.execute("SELECT last_date FROM news_event WHERE event_id=?", (event_id,)).fetchone()
        e2 = conn.execute("SELECT first_date FROM news_event WHERE event_id=?", (r["event_id"],)).fetchone()
        interval = _days_between(e1["last_date"], e2["first_date"]) if e1 and e2 else 0
        related.append({
            "event_id": r["event_id"], "name": r["name"],
            "similarity": min(r["shared"] * 0.2, 1.0),
            "type": "thematic",
            "interval_days": interval,
        })
    return related


def run_event_pipeline(db_path, time_window_days=7, min_items=2, concurrency=3):
    """Full pipeline: detect events → persist → AI profile → link actors → score."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. Clear previous event data (idempotent re-run)
    conn.execute("DELETE FROM event_relation")
    conn.execute("DELETE FROM event_organization")
    conn.execute("DELETE FROM event_person")
    conn.execute("DELETE FROM news_event_link")
    conn.execute("DELETE FROM news_event")
    conn.commit()

    # 2. Detect event clusters
    print("Detecting events...")
    clusters = detect_events(conn, time_window_days, min_items)
    total_items = sum(len(c) for _, c in clusters)
    print(f"Found {len(clusters)} event clusters ({total_items} items)")

    # 3. Create NewsEvent objects + link news items
    event_ids = []
    for name_hint, news_ids in clusters:
        eid = _make_event_id(news_ids)
        dates = sorted(set(
            conn.execute("SELECT broadcast_date FROM news_item WHERE news_id=?", (nid,)).fetchone()["broadcast_date"]
            for nid in news_ids
        ))
        conn.execute("""
            INSERT OR IGNORE INTO news_event (event_id, name, type, first_date, last_date, news_count)
            VALUES (?, ?, 'political', ?, ?, ?)
        """, (eid, name_hint, dates[0], dates[-1], len(news_ids)))

        for nid in news_ids:
            conn.execute(
                "INSERT OR IGNORE INTO news_event_link (news_id, event_id) VALUES (?, ?)",
                (nid, eid),
            )

        # Link persons from news items to event
        placeholders = ",".join("?" * len(news_ids))
        conn.execute(f"""
            INSERT OR IGNORE INTO event_person (event_id, person_id, role)
            SELECT DISTINCT ?, np.person_id, 'mentioned'
            FROM news_person np
            WHERE np.news_id IN ({placeholders})
        """, [eid] + news_ids)

        # Link orgs from news items to event
        conn.execute(f"""
            INSERT OR IGNORE INTO event_organization (event_id, org_id, role)
            SELECT DISTINCT ?, no.org_id, 'mentioned'
            FROM news_organization no
            WHERE no.news_id IN ({placeholders})
        """, [eid] + news_ids)

        event_ids.append(eid)

    conn.commit()
    print(f"Created {len(event_ids)} events")

    # 3a. Promote primary actors: persons appearing most in event's news titles
    for eid in event_ids:
        top_persons = conn.execute("""
            SELECT np.person_id, COUNT(*) as cnt
            FROM news_person np
            JOIN news_event_link nel ON np.news_id = nel.news_id
            WHERE nel.event_id = ?
            GROUP BY np.person_id ORDER BY cnt DESC LIMIT 3
        """, (eid,)).fetchall()
        if top_persons:
            conn.execute(
                "UPDATE event_person SET role = 'primary_actor' WHERE event_id = ? AND person_id = ?",
                (eid, top_persons[0]["person_id"]),
            )
    conn.commit()

    # 3b. Fallback: create single-item events for orphan news items
    orphans = conn.execute("""
        SELECT news_id, title, broadcast_date FROM news_item
        WHERE news_id NOT IN (SELECT news_id FROM news_event_link)
    """).fetchall()
    for orphan in orphans:
        eid = _make_event_id([orphan["news_id"]])
        conn.execute("""
            INSERT OR IGNORE INTO news_event (event_id, name, type, first_date, last_date, news_count)
            VALUES (?, ?, 'political', ?, ?, 1)
        """, (eid, orphan["title"][:80], orphan["broadcast_date"], orphan["broadcast_date"]))
        conn.execute(
            "INSERT OR IGNORE INTO news_event_link (news_id, event_id) VALUES (?, ?)",
            (orphan["news_id"], eid),
        )
        event_ids.append(eid)
    if orphans:
        conn.commit()
        print(f"Added {len(orphans)} orphan single-item events")

    # 4. AI profile generation (concurrent)
    print("Generating AI event profiles...")
    _lock = threading.Lock()

    def _profile_one(eid):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        try:
            profile = generate_event_profile(c, eid)
            if profile:
                c.execute(
                    "UPDATE news_event SET name=?, type=?, summary=?, importance=? WHERE event_id=?",
                    (profile.get("name", f"事件_{eid[:8]}"),
                     profile.get("type", "political"),
                     profile.get("summary", ""),
                     profile.get("importance", "notable"),
                     eid),
                )
                c.commit()
                with _lock:
                    print(f"  {eid[:8]}: {profile.get('name', '?')[:40]}")
                return True
        finally:
            c.close()
        return False

    done = 0
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(_profile_one, eid): eid for eid in event_ids}
        for f in as_completed(futures):
            if f.result():
                done += 1
    print(f"Profiled {done}/{len(event_ids)} events")

    # 5. Compute heat + status + importance
    print("Computing scores...")
    for eid in event_ids:
        heat = compute_heat_score(conn, eid)
        importance = compute_importance(heat)
        status = compute_status(conn, eid)
        # Only override type if AI didn't set it (still default 'political')
        current = conn.execute("SELECT type FROM news_event WHERE event_id=?", (eid,)).fetchone()
        if current and current["type"] == "political":
            etype = classify_event_type(conn, eid)
            conn.execute("UPDATE news_event SET type=? WHERE event_id=?", (etype, eid))
        conn.execute(
            "UPDATE news_event SET heat_score=?, importance=?, status=? WHERE event_id=?",
            (heat, importance, status, eid),
        )
    conn.commit()

    # 6. Find related events
    print("Finding related events...")
    for eid in event_ids:
        related = find_related_events(conn, eid, max_related=5)
        for rel in related:
            conn.execute("""
                INSERT OR IGNORE INTO event_relation
                (source_event_id, target_event_id, similarity_score, relation_type, time_interval_days)
                VALUES (?, ?, ?, ?, ?)
            """, (eid, rel["event_id"], rel["similarity"], rel.get("type", "thematic"),
                  rel.get("interval_days", 0)))
    conn.commit()

    # 7. Final stats
    stats = {
        "events": conn.execute("SELECT COUNT(*) as c FROM news_event").fetchone()["c"],
        "with_summary": conn.execute("SELECT COUNT(*) as c FROM news_event WHERE summary IS NOT NULL AND summary != ''").fetchone()["c"],
        "critical": conn.execute("SELECT COUNT(*) as c FROM news_event WHERE importance='critical'").fetchone()["c"],
        "relations": conn.execute("SELECT COUNT(*) as c FROM event_relation").fetchone()["c"],
    }
    print(f"Pipeline complete: {stats}")
    conn.close()
    return stats
