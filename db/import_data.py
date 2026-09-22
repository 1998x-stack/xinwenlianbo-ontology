#!/usr/bin/env python3
"""Import scraped Markdown into SQLite without silently overwriting enriched records."""

import hashlib
import logging
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DB_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "scraper" / "output"
DATE_FILENAME = re.compile(r"\d{8}\.md\Z")


def make_news_id(broadcast_date, order):
    """Keep the existing date/position-based IDs for database compatibility."""
    raw = f"{broadcast_date}:{order}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_markdown_file(filepath):
    """Read the existing scraper output format: H2 titles separated by --- lines."""
    lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    items = []
    current = None
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                items.append(current)
            current = {"title": line[3:].strip(), "body_lines": []}
        elif current is not None and line.strip() != "---" and not line.startswith("# "):
            if line.strip():
                current["body_lines"].append(line)
    if current is not None:
        items.append(current)
    for item in items:
        item["full_text"] = "\n".join(item.pop("body_lines"))
    return items


def _broadcast_date(filepath):
    if not DATE_FILENAME.fullmatch(filepath.name):
        raise ValueError(f"Invalid scraper filename (expected YYYYMMDD.md): {filepath.name}")
    try:
        date = datetime.strptime(filepath.stem, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"Invalid broadcast date in {filepath.name}") from exc
    if date.strftime("%Y%m%d") != filepath.stem:
        raise ValueError(f"Invalid broadcast date in {filepath.name}")
    return date.strftime("%Y-%m-%d")


def import_data(db_path, data_dir=None):
    """Insert new items atomically; reject a reused date/position with changed text.

    IDs use date and position in the existing database. An edited or reordered
    broadcast therefore requires explicit reconciliation, not INSERT OR IGNORE.
    Returns the count of newly inserted news items.
    """
    data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Scraper output directory not found: {data_dir}")
    md_files = sorted(data_dir.glob("*.md"))
    if not md_files:
        raise ValueError(f"No Markdown broadcasts found in: {data_dir}")

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("SQLite foreign-key enforcement is unavailable")
        inserted = 0
        with conn:  # Any validation or SQL failure rolls back the entire batch.
            for filepath in md_files:
                broadcast_date = _broadcast_date(filepath)
                items = parse_markdown_file(filepath)
                if not items:
                    raise ValueError(f"No news items found in {filepath.name}")
                for order, item in enumerate(items, start=1):
                    title, full_text = item["title"], item["full_text"]
                    if not title or not full_text:
                        raise ValueError(f"Empty title/body in {filepath.name}, item {order}")
                    news_id = make_news_id(broadcast_date, order)
                    existing = conn.execute(
                        "SELECT title, full_text, broadcast_date, order_in_broadcast "
                        "FROM news_item WHERE news_id = ?", (news_id,),
                    ).fetchone()
                    if existing:
                        if existing != (title, full_text, broadcast_date, order):
                            raise ValueError(
                                f"Changed news at {broadcast_date} position {order} "
                                f"(ID {news_id}); reconcile the source and existing "
                                "enrichments before re-importing"
                            )
                        continue
                    conn.execute(
                        "INSERT INTO news_item "
                        "(news_id, title, full_text, broadcast_date, order_in_broadcast, word_count) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (news_id, title, full_text, broadcast_date, order, len(full_text)),
                    )
                    inserted += 1
                logger.info("Checked %s: %d items", filepath.name, len(items))
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise sqlite3.IntegrityError(
                    f"Foreign-key violations in ontology database: {violations[:5]}"
                )
    logger.info("Import complete: %d inserted from %d files", inserted, len(md_files))
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    path = sys.argv[1] if len(sys.argv) > 1 else DB_DIR / "xinwenlianbo.db"
    source = sys.argv[2] if len(sys.argv) > 2 else None
    import_data(path, source)
