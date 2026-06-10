#!/usr/bin/env python3
"""Export the ontology as a graph.json for force-directed visualization."""

import json, sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parent / "xinwenlianbo.db"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"

TOP_PERSONS = 30
TOP_ORGS = 30
TOP_TOPICS = 15
MAX_NEWS = 100


def dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def connect_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = dict_factory
    return conn


def compute_pagerank(nodes, edges, iterations=30, damping=0.85):
    """PageRank on an undirected view of the graph.
    All edges treated as bidirectional so centrality flows both ways
    (news→entity and entity→news). This prevents news nodes from
    being sinkholes with zero incoming links in a bipartite graph."""
    node_ids = {n["id"] for n in nodes}
    # Build undirected adjacency (bidirectional links)
    neighbors = defaultdict(set)
    for e in edges:
        src, tgt = e["source"], e["target"]
        if src in node_ids and tgt in node_ids:
            neighbors[src].add(tgt)
            neighbors[tgt].add(src)  # bidirectional

    N = len(nodes)
    pr = {n["id"]: 1.0 / N for n in nodes}

    for _ in range(iterations):
        new_pr = {}
        for n in nodes:
            nid = n["id"]
            rank = (1 - damping) / N
            for neighbor in neighbors.get(nid, set()):
                deg = len(neighbors.get(neighbor, set()))
                if deg > 0:
                    rank += damping * pr[neighbor] / deg
            new_pr[nid] = rank
        pr = new_pr

    # Normalize to 0-1 range
    max_pr = max(pr.values()) if pr else 1
    min_pr = min(pr.values()) if pr else 0
    if max_pr > min_pr:
        for k in pr:
            pr[k] = (pr[k] - min_pr) / (max_pr - min_pr)
    return pr


def build_graph(conn):
    nodes = []
    edges = []

    # ── News Items (most recent) ──
    news_rows = conn.execute(f"""
        SELECT news_id, title, broadcast_date
        FROM news_item ORDER BY broadcast_date DESC LIMIT {MAX_NEWS}
    """).fetchall()
    news_ids = set()
    for r in news_rows:
        nid = f"news_{r['news_id']}"
        news_ids.add(r["news_id"])
        nodes.append({
            "id": nid, "type": "news", "group": "news",
            "label": r["title"][:40], "date": r["broadcast_date"],
        })

    # ── Top Persons ──
    person_rows = conn.execute(f"""
        SELECT p.person_id, p.name_chinese, p.article_count
        FROM person p ORDER BY p.article_count DESC LIMIT {TOP_PERSONS}
    """).fetchall()
    for r in person_rows:
        pid = f"person_{r['person_id']}"
        nodes.append({
            "id": pid, "type": "person", "group": "person",
            "label": r["name_chinese"], "count": r["article_count"],
        })

    # ── Top Organizations ──
    org_rows = conn.execute(f"""
        SELECT o.org_id, o.name, o.article_count
        FROM organization o ORDER BY o.article_count DESC LIMIT {TOP_ORGS}
    """).fetchall()
    for r in org_rows:
        oid = f"org_{r['org_id']}"
        nodes.append({
            "id": oid, "type": "org", "group": "org",
            "label": r["name"], "count": r["article_count"],
        })

    # ── Topics ──
    topic_rows = conn.execute(f"""
        SELECT topic_id, name, article_count
        FROM topic ORDER BY article_count DESC LIMIT {TOP_TOPICS}
    """).fetchall()
    for r in topic_rows:
        tid = f"topic_{r['topic_id']}"
        nodes.append({
            "id": tid, "type": "topic", "group": "topic",
            "label": r["name"], "count": r["article_count"],
        })

    # ── Edges: News → Person ──
    edge_rows = conn.execute(f"""
        SELECT np.news_id, np.person_id FROM news_person np
        WHERE np.news_id IN ({','.join('?'*len(news_ids))})
          AND np.person_id IN (SELECT person_id FROM person ORDER BY article_count DESC LIMIT {TOP_PERSONS})
    """, list(news_ids)).fetchall()
    seen = set()
    for r in edge_rows:
        key = (r["news_id"], r["person_id"])
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "source": f"news_{r['news_id']}",
            "target": f"person_{r['person_id']}",
            "type": "mentions",
        })

    # ── Edges: News → Org ──
    edge_rows2 = conn.execute(f"""
        SELECT no.news_id, no.org_id FROM news_organization no
        WHERE no.news_id IN ({','.join('?'*len(news_ids))})
          AND no.org_id IN (SELECT org_id FROM organization ORDER BY article_count DESC LIMIT {TOP_ORGS})
    """, list(news_ids)).fetchall()
    seen2 = set()
    for r in edge_rows2:
        key = (r["news_id"], r["org_id"])
        if key in seen2:
            continue
        seen2.add(key)
        edges.append({
            "source": f"news_{r['news_id']}",
            "target": f"org_{r['org_id']}",
            "type": "mentions",
        })

    # ── Edges: News → Topic ──
    edge_rows3 = conn.execute(f"""
        SELECT nt.news_id, nt.topic_id FROM news_topic nt
        WHERE nt.news_id IN ({','.join('?'*len(news_ids))})
    """, list(news_ids)).fetchall()
    seen3 = set()
    for r in edge_rows3:
        key = (r["news_id"], r["topic_id"])
        if key in seen3:
            continue
        seen3.add(key)
        edges.append({
            "source": f"news_{r['news_id']}",
            "target": f"topic_{r['topic_id']}",
            "type": "about",
        })

    # ── Co-occurrence edges: Person ↔ Person ──
    # Persons who appear in the same news item
    cooccur_rows = conn.execute(f"""
        SELECT np1.person_id as p1, np2.person_id as p2, COUNT(*) as weight
        FROM news_person np1
        JOIN news_person np2 ON np1.news_id = np2.news_id AND np1.person_id < np2.person_id
        WHERE np1.person_id IN (SELECT person_id FROM person ORDER BY article_count DESC LIMIT {TOP_PERSONS})
          AND np2.person_id IN (SELECT person_id FROM person ORDER BY article_count DESC LIMIT {TOP_PERSONS})
        GROUP BY p1, p2 HAVING weight >= 2
        ORDER BY weight DESC LIMIT 50
    """).fetchall()
    for r in cooccur_rows:
        edges.append({
            "source": f"person_{r['p1']}",
            "target": f"person_{r['p2']}",
            "type": "co_occur",
            "weight": r["weight"],
        })

    # Compute PageRank and attach to nodes
    pr = compute_pagerank(nodes, edges)
    for n in nodes:
        n["pagerank"] = round(pr.get(n["id"], 0), 4)

    return {"nodes": nodes, "edges": edges}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect_db()
    try:
        graph = build_graph(conn)
        out_path = OUT_DIR / "graph.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False)
        print(f"Exported graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges → {out_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
