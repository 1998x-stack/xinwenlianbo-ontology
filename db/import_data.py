#!/usr/bin/env python3
"""Import scraped markdown files into the SQLite ontology database."""

import hashlib, logging, re, sqlite3, sys
from pathlib import Path

logger = logging.getLogger(__name__)
DB_DIR = Path(__file__).parent
PROJECT_ROOT = DB_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "scraper" / "output"


def make_news_id(broadcast_date, title):
    """Generate a stable news_id from broadcast date + title."""
    raw = f"{broadcast_date}:{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_markdown_file(filepath):
    """Parse a scraper output markdown file into structured news items."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")
    items = []
    current = None

    for line in lines:
        if line.startswith("## "):
            if current and current.get("title"):
                items.append(current)
            current = {"title": line[3:].strip(), "body_lines": []}
        elif current is not None and not line.startswith("# ") and not line.startswith("---"):
            if line.strip():
                current["body_lines"].append(line)

    if current and current.get("title"):
        items.append(current)

    for item in items:
        item["full_text"] = "\n".join(item.get("body_lines", []))

    return items


def import_data(db_path, data_dir=None):
    """Import all markdown files from data_dir into the database."""
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
    data_dir = Path(data_dir)
    db_path = Path(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")

    md_files = sorted(data_dir.glob("*.md"))
    total = 0

    for filepath in md_files:
        date_str = filepath.stem  # YYYYMMDD
        broadcast_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        items = parse_markdown_file(filepath)

        for order, item in enumerate(items):
            news_id = make_news_id(broadcast_date, item["title"])
            conn.execute(
                """INSERT OR IGNORE INTO news_item
                   (news_id, title, full_text, broadcast_date, order_in_broadcast, word_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (news_id, item["title"], item["full_text"], broadcast_date,
                 order + 1, len(item["full_text"])),
            )
            total += 1

        logger.info("Imported %s: %d items", date_str, len(items))

    conn.execute("PRAGMA foreign_key_check")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()
    logger.info("Import complete: %d total items from %d files", total, len(md_files))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    db_path = sys.argv[1] if len(sys.argv) > 1 else str(DB_DIR / "xinwenlianbo.db")
    data_dir = sys.argv[2] if len(sys.argv) > 2 else None
    import_data(db_path, data_dir)
