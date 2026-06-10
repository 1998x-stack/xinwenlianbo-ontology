#!/usr/bin/env python3
"""Scrape xinwenlianbo text from cn.govopendata.com and save as markdown files."""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from config import OUTPUT_DIR, DAYS_TO_SCRAPE
from scraper import scrape_date


def generate_date_list(days_back):
    """Generate list of YYYYMMDD date strings going back `days_back` days."""
    dates = []
    today = datetime.now()
    for i in range(days_back):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y%m%d"))
    return dates


def save_markdown(items, date_str, output_dir):
    """Save scraped news items as a markdown file."""
    dir_path = Path(output_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    filepath = dir_path / f"{date_str}.md"

    broadcast_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# 新闻联播 {broadcast_date}\n\n")
        for item in items:
            f.write(f"## {item['title']}\n\n")
            f.write(f"{item['full_text']}\n\n")
            f.write("---\n\n")

    return filepath


def main():
    parser = argparse.ArgumentParser(description="Scrape xinwenlianbo text from cn.govopendata.com")
    parser.add_argument("--days", type=int, default=DAYS_TO_SCRAPE)
    parser.add_argument("--output", type=str, default=OUTPUT_DIR)
    args = parser.parse_args()

    dates = generate_date_list(args.days)
    print(f"Scraping {len(dates)} dates from cn.govopendata.com...")

    total = 0
    for date_str in dates:
        print(f"  {date_str}...", end=" ", flush=True)
        try:
            items = scrape_date(date_str)
            if items:
                save_markdown(items, date_str, args.output)
                print(f"{len(items)} items")
                total += len(items)
            else:
                print("no items")
        except Exception as e:
            print(f"error: {e}")

    print(f"Done. {total} total items saved to {args.output}")


if __name__ == "__main__":
    main()
