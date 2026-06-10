"""Scrape xinwenlianbo text from cn.govopendata.com using requests + BeautifulSoup."""

import requests
from bs4 import BeautifulSoup
from config import BASE_URL, HEADERS, REQUEST_TIMEOUT


def scrape_date(date_str):
    """Scrape a single date's broadcast. Returns list of dicts with title and full_text."""
    url = f"{BASE_URL}/{date_str}/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  HTTP error: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    main_content = soup.find("main", class_="article-content")
    if not main_content:
        return []

    articles = main_content.find_all("article")
    items = []
    for i, art in enumerate(articles):
        text = art.get_text(strip=True)
        if not text or len(text) < 20:
            continue

        # Extract title: first sentence or first ~80 chars
        title = text[:80]
        for sep in ["。", "，"]:
            idx = text.find(sep, 20)
            if 20 < idx < 80:
                title = text[:idx + 1]
                break

        broadcast_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        items.append({
            "title": title,
            "full_text": text,
            "broadcast_date": broadcast_date,
            "order": i + 1,
            "url": url,
        })

    return items
