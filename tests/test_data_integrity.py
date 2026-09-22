"""Offline regression tests: no network, API key, or existing dataset required."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.export_graph import build_graph, compute_pagerank, dict_factory
from db.import_data import import_data, make_news_id

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")


class DatabaseFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.db_path = self.base / "ontology.db"
        self.source = self.base / "input"
        self.source.mkdir()
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)

    def write(self, day, *items):
        content = f"# 新闻联播 {day}\n\n"
        content += "".join(f"## {title}\n\n{body}\n\n---\n\n" for title, body in items)
        (self.source / f"{day}.md").write_text(content, encoding="utf-8")

    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = dict_factory
        return connection


class ImportTests(DatabaseFixture):
    def test_import_is_idempotent_and_preserves_enrichments(self):
        self.write("20260921", ("第一条", "新闻内容"))
        self.assertEqual(import_data(self.db_path, self.source), 1)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE news_item SET summary = '已校对' ")
        self.assertEqual(import_data(self.db_path, self.source), 0)
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM news_item").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT summary FROM news_item").fetchone()[0], "已校对")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_changed_position_is_rejected_and_batch_rolled_back(self):
        self.write("20260921", ("第一条", "旧内容"))
        import_data(self.db_path, self.source)
        self.write("20260920", ("更早的一条", "原始资料"))
        self.write("20260921", ("第一条", "修改后的内容"))
        with self.assertRaisesRegex(ValueError, "Changed news"):
            import_data(self.db_path, self.source)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT broadcast_date, full_text FROM news_item").fetchall()
        self.assertEqual(rows, [("2026-09-21", "旧内容")])

    def test_invalid_filename_and_empty_article_do_not_commit(self):
        self.write("20260230", ("标题", "正文"))
        with self.assertRaisesRegex(ValueError, "Invalid broadcast date"):
            import_data(self.db_path, self.source)
        (self.source / "20260230.md").unlink()
        self.write("20260921", ("标题", ""))
        with self.assertRaisesRegex(ValueError, "Empty title/body"):
            import_data(self.db_path, self.source)
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM news_item").fetchone()[0], 0)

    def test_foreign_key_check_rejects_existing_invalid_links(self):
        self.write("20260921", ("标题", "正文"))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO news_person (news_id, person_id) "
                         "VALUES ('missing-news', 'missing-person')")
        with self.assertRaises(sqlite3.IntegrityError):
            import_data(self.db_path, self.source)
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM news_item").fetchone()[0], 0)

    def test_missing_source_directory_fails_explicitly(self):
        with self.assertRaises(FileNotFoundError):
            import_data(self.db_path, self.base / "not-found")

    def test_existing_id_format_is_preserved(self):
        self.assertEqual(make_news_id("2026-09-21", 1), make_news_id("2026-09-21", 1))
        self.assertNotEqual(make_news_id("2026-09-21", 1), make_news_id("2026-09-21", 2))


class GraphTests(DatabaseFixture):
    def test_empty_database_gives_empty_graph(self):
        with self.connect() as conn:
            self.assertEqual(build_graph(conn), {"nodes": [], "edges": []})

    def test_edges_have_endpoints_and_topics_are_bounded(self):
        with self.connect() as conn:
            conn.execute("INSERT INTO news_item "
                         "(news_id, title, broadcast_date, order_in_broadcast) "
                         "VALUES ('n1', '标题', '2026-09-21', 1)")
            conn.execute("INSERT INTO person (person_id, name, name_chinese) "
                         "VALUES ('p1', 'Person', '人物')")
            conn.execute("INSERT INTO news_person (news_id, person_id) VALUES ('n1','p1')")
            for number in range(18):
                topic_id = f"t{number:02d}"
                conn.execute("INSERT INTO topic (topic_id, name) VALUES (?, ?)",
                             (topic_id, f"主题{number}"))
                conn.execute("INSERT INTO news_topic (news_id, topic_id) VALUES ('n1', ?)",
                             (topic_id,))
            graph = build_graph(conn)
        ids = {node["id"] for node in graph["nodes"]}
        self.assertEqual(len(ids), len(graph["nodes"]))
        self.assertEqual(sum(node["type"] == "topic" for node in graph["nodes"]), 15)
        self.assertTrue(all(edge["source"] in ids and edge["target"] in ids
                            for edge in graph["edges"]))
        self.assertEqual(len([edge for edge in graph["edges"] if edge["type"] == "about"]), 15)

    def test_isolated_node_rank_mass_is_conserved(self):
        nodes = [{"id": str(i)} for i in range(3)]
        ranks = compute_pagerank(nodes, [], iterations=10)
        self.assertAlmostEqual(sum(ranks.values()), 1.0)
        self.assertTrue(all(abs(rank - 1 / 3) < 1e-10 for rank in ranks.values()))


if __name__ == "__main__":
    unittest.main()
