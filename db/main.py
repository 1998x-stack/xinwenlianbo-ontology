#!/usr/bin/env python3
"""CLI for xinwenlianbo ontology database.

Usage:
    python main.py setup              Create DB + import all data
    python main.py stats              Show database statistics
    python main.py search "关键词"     Search news items by keyword
    python main.py person "人物名"     Show person profile
    python main.py topic "主题名"      Show topic evolution
    python main.py date "YYYY-MM-DD"   Show date summary
    python main.py network "主题名"    Show topic co-occurrence network
    python main.py enhance [--limit N] [--dry-run]   AI enhancement
    python main.py analyze-topic "主题名"             AI topic analysis
"""

import logging, sqlite3, sys
from pathlib import Path

DB_DIR = Path(__file__).parent
sys.path.insert(0, str(DB_DIR))

import queries
from import_data import import_data as run_import
from enhance import enhance_all, enhance_news_item, persist_enhancement, analyze_topic_evolution

DB_PATH = DB_DIR / "xinwenlianbo.db"
SCHEMA_PATH = DB_DIR / "schema.sql"


def _get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def create_database():
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.executescript(schema_sql)
        conn.commit()
        print(f"Database created at: {DB_PATH}")
    except sqlite3.Error as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def is_db_empty():
    try:
        conn = _get_connection()
        count = conn.execute("SELECT COUNT(*) AS cnt FROM news_item").fetchone()["cnt"]
        conn.close()
        return count == 0
    except sqlite3.Error:
        return True


def setup():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    force = "--force-reimport" in sys.argv
    if not DB_PATH.exists():
        print("Creating database...")
        create_database()
    else:
        print("Database already exists.")
    if is_db_empty() or force:
        scraper_dir = DB_DIR.parent / "scraper" / "output"
        md_files = list(scraper_dir.glob("*.md")) if scraper_dir.exists() else []
        if not md_files:
            print(f"No scraped data found in {scraper_dir}")
            print("Run first: cd ../scraper && python main.py --days 30")
            return
        print(f"Importing data from {len(md_files)} files...")
        run_import(str(DB_PATH))
    else:
        print("Database already populated. Use --force-reimport to re-import.")
    print("Setup complete.")


def cmd_stats():
    if not DB_PATH.exists():
        print("Database not found. Run `python main.py setup` first.")
        return
    conn = _get_connection()
    try:
        ni = conn.execute("SELECT COUNT(*) AS c FROM news_item").fetchone()["c"]
        pe = conn.execute("SELECT COUNT(*) AS c FROM person").fetchone()["c"]
        org = conn.execute("SELECT COUNT(*) AS c FROM organization").fetchone()["c"]
        top = conn.execute("SELECT COUNT(*) AS c FROM topic").fetchone()["c"]
        enhanced = conn.execute("SELECT COUNT(*) AS c FROM news_item WHERE summary IS NOT NULL AND summary != ''").fetchone()["c"]
        dates = conn.execute("SELECT COUNT(DISTINCT broadcast_date) AS c FROM news_item").fetchone()["c"]
        print(f"  News Items:     {ni}")
        print(f"  Dates:          {dates}")
        print(f"  Persons:        {pe}")
        print(f"  Organizations:  {org}")
        print(f"  Topics:         {top}")
        print(f"  AI Enhanced:    {enhanced}/{ni}")
    finally:
        conn.close()


def cmd_search(keyword):
    conn = _get_connection()
    try:
        results = queries.search_news(conn, keyword)
        if not results:
            print(f"No items found: {keyword}")
            return
        print(f"Found {len(results)} items: {keyword}\n")
        for r in results:
            excerpt = (r.get("excerpt") or "")[:120].replace("\n", " ")
            print(f"  [{r['broadcast_date']}] {r['title'][:70]}")
            if excerpt:
                print(f"       {excerpt}...")
            print()
    finally:
        conn.close()


def cmd_person(name):
    conn = _get_connection()
    try:
        profile = queries.get_person_profile(conn, name)
        if not profile["person"]:
            print(f"No person found: {name}")
            return
        p = profile["person"]
        print(f"Person: {p['name_chinese']} (ID: {p['person_id']})")
        print(f"  Title: {p.get('title', 'N/A')}")
        if profile["organization"]:
            print(f"  Organization: {profile['organization']['name']}")
        print(f"  Appearances: {len(profile['items'])}")
        if profile["top_topics"]:
            print("  Top topics:")
            for t in profile["top_topics"]:
                print(f"    {t['name']:<20s} {t['cnt']} appearances")
        print("\n  Recent items:")
        for item in profile["items"][:10]:
            print(f"    [{item['broadcast_date']}] {item['title'][:60]}")
    finally:
        conn.close()


def cmd_topic(topic_name):
    conn = _get_connection()
    try:
        evolution = queries.track_topic_evolution(conn, topic_name)
        if not evolution:
            print(f"No data: {topic_name}")
            return
        total = sum(r["news_count"] for r in evolution)
        print(f"Topic: {evolution[0]['topic_name']} ({total} items across {len(evolution)} dates)\n")
        for row in evolution:
            bar = "█" * row["news_count"]
            print(f"  {row['broadcast_date']}  {row['news_count']:>2d} {bar}")
    finally:
        conn.close()


def cmd_date(date_str):
    conn = _get_connection()
    try:
        summary = queries.get_date_summary(conn, date_str)
        if not summary["items"]:
            print(f"No items for date: {date_str}")
            return
        print(f"Date: {date_str} ({summary['total']} items)\n")
        for item in summary["items"]:
            people = ", ".join(item.get("people", []))
            orgs = ", ".join(item.get("organizations", []))
            print(f"  #{item['order_in_broadcast']} {item['title'][:70]}")
            if people:
                print(f"     People: {people}")
            if orgs:
                print(f"     Orgs: {orgs}")
            print()
    finally:
        conn.close()


def cmd_network(topic_name):
    conn = _get_connection()
    try:
        network = queries.get_topic_network(conn, topic_name)
        if not network["focus_topic"]:
            print(f"No topic found: {topic_name}")
            return
        t = network["focus_topic"]
        print(f"Topic network: {t['name']} ({network['total_items']} items)\n")
        for rt in network["related_topics"]:
            bar = "█" * min(rt["cooccurrence_count"], 20)
            print(f"  {rt['name']:<20s} {rt['cooccurrence_count']:>2d} {bar}")
    finally:
        conn.close()


def cmd_enhance():
    conn = _get_connection()
    limit = 0
    dry_run = False
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    try:
        stats = enhance_all(conn, limit=limit, dry_run=dry_run)
        print(f"Done: {stats}")
    except RuntimeError as e:
        if "DEEPSEEK_API_KEY" in str(e):
            print("Error: DEEPSEEK_API_KEY not set.")
        else:
            raise
    finally:
        conn.close()


def cmd_analyze_topic(topic_name):
    conn = _get_connection()
    try:
        evolution = queries.track_topic_evolution(conn, topic_name)
        if not evolution:
            print(f"No data: {topic_name}")
            return
        total = sum(r["news_count"] for r in evolution)
        print(f"Topic: {topic_name} ({total} items)\n")
        for row in evolution:
            print(f"  {row['broadcast_date']}  {row['news_count']:>2d}")
        print("\n" + "=" * 60)
        print(analyze_topic_evolution(conn, topic_name))
    except RuntimeError as e:
        if "DEEPSEEK_API_KEY" in str(e):
            print("AI analysis unavailable: DEEPSEEK_API_KEY not set.")
        else:
            raise
    finally:
        conn.close()


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "setup": setup()
    elif cmd == "stats": cmd_stats()
    elif cmd == "search" and len(sys.argv) > 2: cmd_search(sys.argv[2])
    elif cmd == "person" and len(sys.argv) > 2: cmd_person(sys.argv[2])
    elif cmd == "topic" and len(sys.argv) > 2: cmd_topic(sys.argv[2])
    elif cmd == "date" and len(sys.argv) > 2: cmd_date(sys.argv[2])
    elif cmd == "network" and len(sys.argv) > 2: cmd_network(sys.argv[2])
    elif cmd == "enhance": cmd_enhance()
    elif cmd == "analyze-topic" and len(sys.argv) > 2: cmd_analyze_topic(sys.argv[2])
    elif cmd in ("-h", "--help"): print_usage()
    else: print_usage(); sys.exit(1)


if __name__ == "__main__":
    main()
