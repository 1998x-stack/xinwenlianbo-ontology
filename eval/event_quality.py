"""Diagnostic metrics for an exported news-to-event assignment.

These measures reveal *risk*, not truth: gold-labeled event identities are
required before computing actual clustering precision/recall.
"""

import argparse
import json
from pathlib import Path


def assess(events, news):
    if not isinstance(events, list) or not isinstance(news, list):
        raise ValueError("events and news must be arrays")
    all_news = {item["news_id"] for item in news}
    if len(all_news) != len(news):
        raise ValueError("duplicate news_id in source export")

    sizes = []
    assigned = set()
    dangling = set()
    for event in events:
        members = [item["news_id"] for item in event.get("items", [])]
        if len(members) != len(set(members)):
            raise ValueError(f"duplicate membership within {event.get('event_id')}")
        sizes.append(len(members))
        assigned.update(members)
        dangling.update(set(members) - all_news)

    total = len(news)
    largest = max(sizes, default=0)
    report = {
        "news_count": total,
        "event_count": len(events),
        "assigned_unique_news": len(assigned & all_news),
        "unassigned_news": len(all_news - assigned),
        "dangling_memberships": len(dangling),
        "largest_event_size": largest,
        "largest_event_share": round(largest / total, 4) if total else 0.0,
        "singleton_events": sum(size == 1 for size in sizes),
        "average_event_size": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
        # Heuristic audit trigger only; NOT an event-quality score.
        "requires_overmerge_review": total > 0 and largest / total > 0.25,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Diagnose event-cluster concentration in static exports")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    args = parser.parse_args()
    events = json.loads((args.data_dir / "events.json").read_text(encoding="utf-8"))
    with (args.data_dir / "news_items.jsonl").open(encoding="utf-8") as source:
        news = [json.loads(line) for line in source if line.strip()]
    print(json.dumps(assess(events, news), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
