#!/usr/bin/env python3
"""Export the xinwenlianbo ontology database to JSONL and summary JSON files."""

import json, sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "xinwenlianbo.db"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"


def dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def connect_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = dict_factory
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def export_news_items(conn):
    rows = conn.execute("""
        SELECT news_id, title, full_text, broadcast_date, order_in_broadcast,
               summary, keywords, tags, word_count, url
        FROM news_item ORDER BY broadcast_date, order_in_broadcast
    """).fetchall()

    out = []
    for row in rows:
        nid = row["news_id"]

        # People
        people_rows = conn.execute("""
            SELECT p.name, p.name_chinese, p.title
            FROM person p JOIN news_person np ON p.person_id = np.person_id
            WHERE np.news_id = ? ORDER BY p.name_chinese
        """, (nid,)).fetchall()
        people = [{"name": r["name"], "name_chinese": r["name_chinese"], "title": r["title"]} for r in people_rows]

        # Organizations
        org_rows = conn.execute("""
            SELECT o.name, o.type FROM organization o
            JOIN news_organization no ON o.org_id = no.org_id
            WHERE no.news_id = ?
        """, (nid,)).fetchall()
        orgs = [{"name": r["name"], "type": r["type"]} for r in org_rows]

        # Topics
        topic_rows = conn.execute("""
            SELECT t.topic_id, t.name, t.category, nt.relevance_score AS relevance
            FROM topic t JOIN news_topic nt ON t.topic_id = nt.topic_id
            WHERE nt.news_id = ? ORDER BY nt.relevance_score DESC
        """, (nid,)).fetchall()
        topics = [{"topic_id": r["topic_id"], "name": r["name"], "category": r["category"], "relevance": r["relevance"]} for r in topic_rows]

        # Keywords
        keywords = []
        if row["keywords"]:
            try:
                keywords = json.loads(row["keywords"])
            except (json.JSONDecodeError, TypeError):
                keywords = []

        # Tags
        tags = {}
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except (json.JSONDecodeError, TypeError):
                tags = {}

        summary = row["summary"]
        excerpt = summary if summary else (row["full_text"] or "")[:200]

        out.append({
            "news_id": nid,
            "title": row["title"],
            "broadcast_date": row["broadcast_date"],
            "order_in_broadcast": row["order_in_broadcast"],
            "people": people,
            "organizations": orgs,
            "topics": topics,
            "keywords": keywords,
            "tags": tags,
            "summary": summary,
            "excerpt": excerpt,
            "word_count": row["word_count"],
            "url": row["url"],
        })

    out_path = OUT_DIR / "news_items.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for item in out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Exported {len(out)} items to {out_path}")
    return out


def export_topics(conn):
    rows = conn.execute("SELECT topic_id, name, category, article_count FROM topic ORDER BY article_count DESC").fetchall()
    out = []
    for r in rows:
        date_cnt = conn.execute("""
            SELECT COUNT(DISTINCT n.broadcast_date) AS cnt
            FROM news_topic nt JOIN news_item n ON n.news_id = nt.news_id
            WHERE nt.topic_id = ?
        """, (r["topic_id"],)).fetchone()["cnt"]
        out.append({"topic_id": r["topic_id"], "name": r["name"], "category": r["category"], "article_count": r["article_count"] or 0, "date_count": date_cnt})

    out_path = OUT_DIR / "topics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(out)} topics to {out_path}")


def export_dates(conn):
    rows = conn.execute("""
        SELECT broadcast_date, COUNT(*) AS item_count,
               SUM(CASE WHEN summary IS NOT NULL AND summary != '' THEN 1 ELSE 0 END) AS enhanced_count
        FROM news_item GROUP BY broadcast_date ORDER BY broadcast_date
    """).fetchall()
    out = [{"date": r["broadcast_date"], "item_count": r["item_count"], "enhanced_count": r["enhanced_count"]} for r in rows]

    out_path = OUT_DIR / "dates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(out)} dates to {out_path}")


# ---------------------------------------------------------------------------
# Events  (events.json) — Phase 2
# ---------------------------------------------------------------------------

def export_events(conn):
    """Export events with linked items, actors, and relations for dashboard."""
    rows = conn.execute("""
        SELECT * FROM news_event ORDER BY heat_score DESC
    """).fetchall()

    out = []
    for row in rows:
        eid = row["event_id"]

        items = conn.execute("""
            SELECT n.news_id, n.title, n.broadcast_date
            FROM news_item n
            JOIN news_event_link nel ON n.news_id = nel.news_id
            WHERE nel.event_id = ? ORDER BY n.broadcast_date
        """, (eid,)).fetchall()
        event_items = [{"news_id": r["news_id"], "title": r["title"], "date": r["broadcast_date"]} for r in items]

        persons = conn.execute("""
            SELECT p.name_chinese, ep.role FROM person p
            JOIN event_person ep ON p.person_id = ep.person_id
            WHERE ep.event_id = ? AND ep.role = 'primary_actor' LIMIT 10
        """, (eid,)).fetchall()
        event_persons = [{"name": r["name_chinese"], "role": r["role"]} for r in persons]

        related = conn.execute("""
            SELECT e.event_id, e.name, er.similarity_score, er.relation_type
            FROM news_event e
            JOIN event_relation er ON e.event_id = er.target_event_id
            WHERE er.source_event_id = ? ORDER BY er.similarity_score DESC LIMIT 5
        """, (eid,)).fetchall()
        event_related = [{"event_id": r["event_id"], "name": r["name"], "similarity": r["similarity_score"], "type": r["relation_type"]} for r in related]

        out.append({
            "event_id": eid,
            "name": row["name"],
            "type": row["type"],
            "importance": row["importance"],
            "status": row["status"],
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "news_count": row["news_count"],
            "summary": row["summary"],
            "heat_score": row["heat_score"],
            "items": event_items,
            "key_persons": event_persons,
            "related_events": event_related,
        })

    out_path = OUT_DIR / "events.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(out)} events to {out_path}")
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect_db()
    try:
        export_news_items(conn)
        export_topics(conn)
        export_dates(conn)
        export_events(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
