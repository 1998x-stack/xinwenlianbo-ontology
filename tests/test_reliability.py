"""Regression tests for schema migration, provenance, and atomic event publishing."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db import main as cli
from db.event_engine import run_event_pipeline
from db.import_data import import_data

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_V1 = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
SCHEMA_V2 = (ROOT / "db" / "schema_v2.sql").read_text(encoding="utf-8")


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.database = self.base / "news.db"
        self.input_dir = self.base / "input"
        self.input_dir.mkdir()

    def initialize(self):
        with sqlite3.connect(self.database) as connection:
            connection.executescript(SCHEMA_V1)
            connection.executescript(SCHEMA_V2)
            connection.execute(
                "INSERT INTO news_item(news_id,title,full_text,broadcast_date) "
                "VALUES ('n1','第一条','测试原文','2026-09-20')"
            )
            connection.execute(
                "INSERT INTO news_event(event_id,name,type,first_date,last_date) "
                "VALUES ('old','历史事件','social','2026-09-20','2026-09-20')"
            )
            connection.execute(
                "INSERT INTO news_event_link(news_id,event_id) VALUES ('n1','old')"
            )

    def test_database_setup_includes_event_schema(self):
        with patch.object(cli, "DB_PATH", self.database):
            cli.create_database()
            cli.create_database()
        with sqlite3.connect(self.database) as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertTrue({"news_item", "news_event", "event_relation"}.issubset(tables))

    def test_markdown_source_url_survives_import_and_backfills(self):
        path = self.input_dir / "20260920.md"
        path.write_text("# 新闻联播 2026-09-20\n\n## 第一条\n\n正文\n\n---\n", encoding="utf-8")
        with sqlite3.connect(self.database) as connection:
            connection.executescript(SCHEMA_V1)
        self.assertEqual(import_data(self.database, self.input_dir), 1)
        path.write_text(
            "# 新闻联播 2026-09-20\n\n## 第一条\n\n"
            "<!-- source_url: https://example.org/archive/20260920/ -->\n\n"
            "正文\n\n---\n", encoding="utf-8"
        )
        self.assertEqual(import_data(self.database, self.input_dir), 0)
        with sqlite3.connect(self.database) as connection:
            url, body = connection.execute("SELECT url,full_text FROM news_item").fetchone()
            self.assertEqual(url, "https://example.org/archive/20260920/")
            self.assertEqual(body, "正文")

    def test_stage_failure_does_not_destroy_published_events(self):
        self.initialize()
        with patch("db.event_engine._run_event_pipeline_in_stage",
                   side_effect=RuntimeError("simulated model failure")):
            with self.assertRaisesRegex(RuntimeError, "simulated model failure"):
                run_event_pipeline(self.database)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute(
                "SELECT event_id FROM news_event").fetchall(), [("old",)])
            self.assertEqual(connection.execute(
                "SELECT news_id,event_id FROM news_event_link").fetchall(),
                [("n1", "old")])

    def test_failed_model_profile_cannot_replace_previous_events(self):
        self.initialize()
        with patch("db.event_engine.generate_event_profile", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Event profiles incomplete"):
                run_event_pipeline(self.database, concurrency=1)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute(
                "SELECT event_id FROM news_event").fetchall(), [("old",)])

    def test_publish_replaces_all_event_tables_as_one_generation(self):
        self.initialize()

        def build_stage(path, **kwargs):
            with sqlite3.connect(path) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("DELETE FROM news_event_link")
                connection.execute("DELETE FROM news_event")
                connection.execute(
                    "INSERT INTO news_event(event_id,name,type,first_date,last_date) "
                    "VALUES ('new','新事件','social','2026-09-20','2026-09-20')"
                )
                connection.execute(
                    "INSERT INTO news_event_link(news_id,event_id) VALUES ('n1','new')"
                )
            return {"events": 1}

        with patch("db.event_engine._run_event_pipeline_in_stage", side_effect=build_stage):
            self.assertEqual(run_event_pipeline(self.database), {"events": 1})
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute(
                "SELECT event_id FROM news_event").fetchall(), [("new",)])
            self.assertEqual(connection.execute(
                "SELECT news_id,event_id FROM news_event_link").fetchall(),
                [("n1", "new")])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
