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
    except requests.RequestException:
        # Distinguish a failed request from a legitimately empty broadcast.
        raise

    soup = BeautifulSoup(r.text, "html.parser")
    main_content = soup.find("main", class_="article-content")
    if not main_content:
        return []

    articles = main_content.find_all("article", class_="content-section")
    items = []
    for i, art in enumerate(articles):
        # Extract title from <h2 class="content-heading">
        heading = art.find("h2", class_="content-heading")
        if not heading:
            heading = art.find("h2")
        title = heading.get_text(strip=True) if heading else ""

        # Extract body from <div class="content-body"> <p> tags
        body_div = art.find("div", class_="content-body")
        if body_div:
            paragraphs = body_div.find_all("p")
            body_text = "\n".join(p.get_text(strip=True) for p in paragraphs)
        else:
            body_text = ""

        if not title or len(body_text) < 20:
            continue
        # Some source pages render an error message in a valid article container.
        invalid_markers = ("网络原因或无此页面", "请稍后尝试", "页面不存在", "访问出错")
        if any(marker in title for marker in invalid_markers):
            continue

        broadcast_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        items.append({
            "title": title,
            "full_text": body_text,
            "broadcast_date": broadcast_date,
            "order": i + 1,
            "url": url,
        })

    return items
