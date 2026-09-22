#!/usr/bin/env python3
"""Export a bounded, internally consistent graph for the static visualizer."""

import json
import sqlite3
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "xinwenlianbo.db"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"
TOP_PERSONS = 30
TOP_ORGS = 30
TOP_TOPICS = 15
MAX_NEWS = 100


def dict_factory(cursor, row):
    return {column[0]: row[i] for i, column in enumerate(cursor.description)}


def connect_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = dict_factory
    return conn


def compute_pagerank(nodes, edges, iterations=30, damping=0.85):
    """Undirected PageRank; redistribute isolated-node mass on each iteration."""
    node_ids = {node["id"] for node in nodes}
    if not node_ids:
        return {}
    neighbors = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source, target = edge["source"], edge["target"]
        if source in node_ids and target in node_ids and source != target:
            neighbors[source].add(target)
            neighbors[target].add(source)

    size = len(node_ids)
    rank = dict.fromkeys(node_ids, 1.0 / size)
    for _ in range(iterations):
        dangling = sum(rank[node_id] for node_id, links in neighbors.items() if not links)
        updated = {
            node_id: (1.0 - damping) / size + damping * dangling / size
            for node_id in node_ids
        }
        for source, links in neighbors.items():
            if links:
                contribution = damping * rank[source] / len(links)
                for target in links:
                    updated[target] += contribution
        rank = updated

    # Preserve the existing visualizer's normalized [0, 1] scale.
    minimum, maximum = min(rank.values()), max(rank.values())
    if maximum > minimum:
        return {node_id: (value - minimum) / (maximum - minimum)
                for node_id, value in rank.items()}
    return dict.fromkeys(node_ids, 1.0 / size)


def _links(conn, table, entity_column, news_ids):
    """Fetch unique relations only for the selected broadcasts."""
    if not news_ids:
        return set()
    placeholders = ",".join("?" for _ in news_ids)
    # Table names are internal constants supplied by build_graph, never input.
    rows = conn.execute(
        f"SELECT news_id, {entity_column} FROM {table} "
        f"WHERE news_id IN ({placeholders})", tuple(news_ids),
    ).fetchall()
    return {(row["news_id"], row[entity_column]) for row in rows}


def _selected_entities(conn, table, id_column, label_column, links, maximum):
    counts = Counter(entity_id for _, entity_id in links)
    if not counts:
        return [], set()
    chosen = [entity_id for entity_id, _ in counts.most_common(maximum)]
    placeholders = ",".join("?" for _ in chosen)
    rows = conn.execute(
        f"SELECT {id_column}, {label_column} FROM {table} "
        f"WHERE {id_column} IN ({placeholders})", chosen,
    ).fetchall()
    by_id = {row[id_column]: row for row in rows}
    selected = [by_id[entity_id] for entity_id in chosen if entity_id in by_id]
    return selected, {row[id_column] for row in selected}


def build_graph(conn):
    news = conn.execute(
        "SELECT news_id, title, broadcast_date FROM news_item "
        "ORDER BY broadcast_date DESC, order_in_broadcast, news_id LIMIT ?",
        (MAX_NEWS,),
    ).fetchall()
    if not news:
        return {"nodes": [], "edges": []}
    news_ids = {row["news_id"] for row in news}
    nodes = [
        {"id": f"news_{row['news_id']}", "type": "news", "group": "news",
         "label": row["title"][:40], "date": row["broadcast_date"]}
        for row in news
    ]

    person_links = _links(conn, "news_person", "person_id", news_ids)
    org_links = _links(conn, "news_organization", "org_id", news_ids)
    topic_links = _links(conn, "news_topic", "topic_id", news_ids)
    persons, person_ids = _selected_entities(
        conn, "person", "person_id", "name_chinese", person_links, TOP_PERSONS
    )
    orgs, org_ids = _selected_entities(
        conn, "organization", "org_id", "name", org_links, TOP_ORGS
    )
    topics, topic_ids = _selected_entities(
        conn, "topic", "topic_id", "name", topic_links, TOP_TOPICS
    )
    for prefix, kind, label, id_key, rows, links in (
        ("person", "person", "name_chinese", "person_id", persons, person_links),
        ("org", "org", "name", "org_id", orgs, org_links),
        ("topic", "topic", "name", "topic_id", topics, topic_links),
    ):
        counts = Counter(entity_id for _, entity_id in links)
        for row in rows:
            entity_id = row[id_key]
            nodes.append({
                "id": f"{prefix}_{entity_id}", "type": kind, "group": kind,
                "label": row[label], "count": counts[entity_id],
            })

    edges = []
    for links, selected, prefix, relation in (
        (person_links, person_ids, "person", "mentions"),
        (org_links, org_ids, "org", "mentions"),
        (topic_links, topic_ids, "topic", "about"),
    ):
        for news_id, entity_id in sorted(links):
            if entity_id in selected:
                edges.append({
                    "source": f"news_{news_id}", "target": f"{prefix}_{entity_id}",
                    "type": relation,
                })

    people_by_news = defaultdict(set)
    for news_id, person_id in person_links:
        if person_id in person_ids:
            people_by_news[news_id].add(person_id)
    pairs = Counter(
        pair for persons_in_news in people_by_news.values()
        for pair in combinations(sorted(persons_in_news), 2)
    )
    for (first, second), weight in sorted(
        pairs.items(), key=lambda item: (-item[1], item[0])
    )[:50]:
        if weight >= 2:
            edges.append({
                "source": f"person_{first}", "target": f"person_{second}",
                "type": "co_occur", "weight": weight,
            })

    node_ids = {node["id"] for node in nodes}
    assert all(edge["source"] in node_ids and edge["target"] in node_ids
               for edge in edges), "Graph export contains dangling edges"
    pagerank = compute_pagerank(nodes, edges)
    for node in nodes:
        node["pagerank"] = round(pagerank[node["id"]], 4)
    return {"nodes": nodes, "edges": edges}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect_db()
    try:
        graph = build_graph(conn)
    finally:
        conn.close()
    output = OUT_DIR / "graph.json"
    with output.open("w", encoding="utf-8") as stream:
        json.dump(graph, stream, ensure_ascii=False)
    print(f"Exported graph: {len(graph['nodes'])} nodes, "
          f"{len(graph['edges'])} edges -> {output}")


if __name__ == "__main__":
    main()
