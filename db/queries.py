"""Query functions for the xinwenlianbo ontology database."""

import sqlite3


def _rows_to_dicts(rows):
    """Convert sqlite3.Row objects to plain dicts."""
    return [dict(r) for r in rows]


def search_news(conn: sqlite3.Connection, keyword: str, limit: int = 50) -> list[dict]:
    """Full-text search on news title and body, ranked by relevance."""
    cursor = conn.execute("""
        SELECT n.news_id, n.title, n.broadcast_date,
               n.word_count, n.url,
               SUBSTR(n.full_text, 1, 200) AS excerpt,
               CASE WHEN n.title LIKE '%' || ? || '%' THEN 2 ELSE 1 END AS relevance
        FROM news_item n
        WHERE n.title LIKE '%' || ? || '%' OR n.full_text LIKE '%' || ? || '%'
        ORDER BY relevance DESC, n.broadcast_date DESC
        LIMIT ?
    """, (keyword, keyword, keyword, limit))
    return _rows_to_dicts(cursor.fetchall())


def get_person_profile(conn: sqlite3.Connection, person_name: str) -> dict:
    """Get a person's profile: metadata, news appearances, topic distribution, organization."""
    cursor = conn.execute(
        "SELECT * FROM person WHERE name_chinese = ? OR name = ?",
        (person_name, person_name),
    )
    person = cursor.fetchone()
    if not person:
        cursor = conn.execute(
            "SELECT * FROM person WHERE name_chinese LIKE ? OR name LIKE ?",
            (f"%{person_name}%", f"%{person_name}%"),
        )
        person = cursor.fetchone()
    if not person:
        return {"person": None, "items": [], "top_topics": [], "organization": None}

    person = dict(person)
    pid = person["person_id"]

    cursor = conn.execute("""
        SELECT n.news_id, n.title, n.broadcast_date, n.summary
        FROM news_item n
        JOIN news_person np ON n.news_id = np.news_id
        WHERE np.person_id = ?
        ORDER BY n.broadcast_date DESC
    """, (pid,))
    items = _rows_to_dicts(cursor.fetchall())

    cursor = conn.execute("""
        SELECT t.topic_id, t.name, COUNT(*) AS cnt
        FROM topic t
        JOIN news_topic nt ON t.topic_id = nt.topic_id
        JOIN news_person np ON nt.news_id = np.news_id
        WHERE np.person_id = ?
        GROUP BY t.topic_id ORDER BY cnt DESC LIMIT 10
    """, (pid,))
    top_topics = _rows_to_dicts(cursor.fetchall())

    org = None
    if person.get("organization_id"):
        cursor = conn.execute("SELECT * FROM organization WHERE org_id = ?", (person["organization_id"],))
        org_row = cursor.fetchone()
        if org_row:
            org = dict(org_row)

    return {"person": person, "items": items, "top_topics": top_topics, "organization": org}


def track_topic_evolution(conn: sqlite3.Connection, topic_name: str) -> list[dict]:
    """Track how a topic's coverage evolves across dates."""
    cursor = conn.execute(
        "SELECT * FROM topic WHERE name = ? OR name LIKE ?",
        (topic_name, f"%{topic_name}%"),
    )
    topic_row = cursor.fetchone()
    if not topic_row:
        return []
    tid = topic_row["topic_id"]

    cursor = conn.execute("""
        SELECT n.broadcast_date, COUNT(*) AS news_count,
               GROUP_CONCAT(n.title, ' || ') AS titles
        FROM news_item n
        JOIN news_topic nt ON n.news_id = nt.news_id
        WHERE nt.topic_id = ?
        GROUP BY n.broadcast_date
        ORDER BY n.broadcast_date
    """, (tid,))
    results = _rows_to_dicts(cursor.fetchall())
    for r in results:
        r["topic_id"] = tid
        r["topic_name"] = topic_row["name"]
    return results


def get_date_summary(conn: sqlite3.Connection, date_str: str) -> dict:
    """Get all news items for a specific broadcast date with people and orgs."""
    cursor = conn.execute("""
        SELECT n.news_id, n.title, n.order_in_broadcast, n.summary, n.word_count
        FROM news_item n
        WHERE n.broadcast_date = ?
        ORDER BY n.order_in_broadcast
    """, (date_str,))
    items = _rows_to_dicts(cursor.fetchall())

    for item in items:
        cursor = conn.execute("""
            SELECT p.name_chinese FROM person p
            JOIN news_person np ON p.person_id = np.person_id
            WHERE np.news_id = ?
        """, (item["news_id"],))
        item["people"] = [r["name_chinese"] for r in cursor.fetchall()]

        cursor = conn.execute("""
            SELECT o.name FROM organization o
            JOIN news_organization no ON o.org_id = no.org_id
            WHERE no.news_id = ?
        """, (item["news_id"],))
        item["organizations"] = [r["name"] for r in cursor.fetchall()]

    return {"date": date_str, "items": items, "total": len(items)}


def get_topic_network(conn: sqlite3.Connection, topic_name: str, min_cooccurrence: int = 1) -> dict:
    """Find topics that co-occur in news items with the given topic."""
    cursor = conn.execute(
        "SELECT * FROM topic WHERE name = ? OR name LIKE ?",
        (topic_name, f"%{topic_name}%"),
    )
    topic_row = cursor.fetchone()
    if not topic_row:
        return {"focus_topic": None, "related_topics": [], "total_items": 0}

    topic = dict(topic_row)
    tid = topic["topic_id"]

    cursor = conn.execute("SELECT COUNT(*) AS cnt FROM news_topic WHERE topic_id = ?", (tid,))
    total = cursor.fetchone()["cnt"]

    cursor = conn.execute("""
        SELECT t.topic_id, t.name, t.category, COUNT(*) AS cooccurrence_count
        FROM topic t
        JOIN news_topic nt2 ON t.topic_id = nt2.topic_id
        WHERE nt2.news_id IN (SELECT nt1.news_id FROM news_topic nt1 WHERE nt1.topic_id = ?)
          AND t.topic_id != ?
        GROUP BY t.topic_id
        HAVING cooccurrence_count >= ?
        ORDER BY cooccurrence_count DESC LIMIT 20
    """, (tid, tid, min_cooccurrence))
    related = _rows_to_dicts(cursor.fetchall())

    return {"focus_topic": topic, "related_topics": related, "total_items": total}


def compare_coverage(conn: sqlite3.Connection, person_names: list[str]) -> dict:
    """Compare how different people are covered across broadcasts."""
    result = {}
    for name in person_names:
        cursor = conn.execute("""
            SELECT n.news_id, n.title, n.broadcast_date, n.summary
            FROM news_item n
            JOIN news_person np ON n.news_id = np.news_id
            JOIN person p ON np.person_id = p.person_id
            WHERE p.name_chinese = ? OR p.name LIKE ? OR p.name_chinese LIKE ?
            ORDER BY n.broadcast_date
        """, (name, name, f"%{name}%"))
        result[name] = _rows_to_dicts(cursor.fetchall())
    return result
