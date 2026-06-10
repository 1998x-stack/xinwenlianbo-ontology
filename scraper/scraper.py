import json, asyncio, os, urllib.request, re
from datetime import datetime, timedelta

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
import websockets
from config import BASE_URL, CHROME_CDP_URL, PAGE_LOAD_WAIT


def _get_ws_url():
    resp = urllib.request.urlopen(f"{CHROME_CDP_URL}/json")
    targets = json.loads(resp.read())
    pages = [t for t in targets if t["type"] == "page"]
    return pages[0]["webSocketDebuggerUrl"].replace("localhost", "127.0.0.1")


async def _scrape_date_page(ws, date_str):
    url = f"{BASE_URL}/{date_str}/"
    await ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
    await ws.recv()
    await asyncio.sleep(PAGE_LOAD_WAIT)

    expr = "document.body.innerText"
    await ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": expr}}))
    r = await ws.recv()
    text = json.loads(r).get("result", {}).get("result", {}).get("value", "")
    return text


def parse_news_items(raw_text, date_str):
    """Parse broadcast text into structured news items.
    News items in Xinwen Lianbo are typically separated by section headers
    or numbered segments. We look for patterns like '1.', '2.' or section titles."""
    items = []
    lines = raw_text.strip().split("\n")
    current = None
    title_pattern = re.compile(r"^\s*(\d+)[\.、）\)]\s*(.+)")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = title_pattern.match(line)
        if m:
            if current and current.get("title"):
                items.append(current)
            current = {"title": m.group(2).strip(), "order": int(m.group(1)),
                       "broadcast_date": _format_date(date_str), "body_lines": []}
        elif current is not None:
            current["body_lines"].append(line)

    if current and current.get("title"):
        items.append(current)

    for item in items:
        item["full_text"] = "\n".join(item.get("body_lines", []))

    return items


def _format_date(ymd_str):
    return f"{ymd_str[:4]}-{ymd_str[4:6]}-{ymd_str[6:8]}"


async def scrape_date(date_str):
    """Scrape a single date's broadcast. Returns list of news item dicts."""
    ws_url = _get_ws_url()
    async with websockets.connect(ws_url, max_size=10_000_000) as ws:
        text = await _scrape_date_page(ws, date_str)
    items = parse_news_items(text, date_str)
    return items
