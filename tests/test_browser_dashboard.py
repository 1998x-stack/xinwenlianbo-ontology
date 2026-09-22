"""Optional real-browser regression suite; executed in the dedicated CI browser job."""

import functools
import json
import shutil
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
# This is intentionally inert fixture input: it must be rendered as text, not markup.
HOSTILE = '<img src=x onerror="window.__injected=true">'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@unittest.skipUnless(sync_playwright is not None, "Install playwright for browser tests")
class BrowserDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        base = Path(cls.temp.name)
        (base / "visualize").mkdir()
        (base / "data").mkdir()
        shutil.copy2(ROOT / "visualize" / "index.html", base / "visualize" / "index.html")
        item = {
            "news_id": "safe-1", "title": HOSTILE, "broadcast_date": "2026-09-21",
            "order_in_broadcast": 1, "summary": HOSTILE, "excerpt": HOSTILE,
            "keywords": [HOSTILE], "people": [{"name_chinese": HOSTILE}],
            "organizations": [{"name": HOSTILE}],
            "topics": [{"topic_id": "t-1", "name": HOSTILE}],
            "url": "javascript:alert(1)",
        }
        (base / "data" / "news_items.jsonl").write_text(
            json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8",
        )
        for filename, value in (
            ("topics.json", [{"topic_id": "t-1", "name": HOSTILE, "article_count": 1}]),
            ("dates.json", [{"date": "2026-09-21", "item_count": 1}]),
            ("events.json", [{"event_id": "e-1", "name": HOSTILE,
                               "first_date": "2026-09-21", "last_date": "2026-09-21",
                               "news_count": 1, "status": "developing", "summary": HOSTILE,
                               "items": [{"news_id": "safe-1", "title": HOSTILE,
                                          "date": "2026-09-21"}]}]),
        ):
            (base / "data" / filename).write_text(
                json.dumps(value, ensure_ascii=False), encoding="utf-8",
            )
        handler = functools.partial(QuietHandler, directory=str(base))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/visualize/index.html"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def test_fixture_text_in_list_and_modal_does_not_create_html(self):
        self.page.goto(self.url)
        self.page.locator("#status").get_by_text("加载完成", exact=False).wait_for()
        self.assertIn(HOSTILE, self.page.locator("#news .entry").first.inner_text())
        self.assertEqual(self.page.locator("#news img, #topics img, #people img").count(), 0)
        self.page.locator("#news .entry").first.click()
        self.assertIn(HOSTILE, self.page.locator("#detail-title").inner_text())
        self.assertEqual(self.page.locator("#detail-body img, #detail-body a").count(), 0)
        self.assertIsNone(self.page.evaluate("window.__injected"))
        self.page.keyboard.press("Escape")
        self.assertFalse(self.page.locator("#detail").evaluate("element => element.open"))

    def test_url_hash_search_is_rendered_as_text(self):
        self.page.goto(self.url + "#search=" + quote(HOSTILE))
        self.page.locator("#status").get_by_text("加载完成", exact=False).wait_for()
        self.assertIn(HOSTILE, self.page.locator("#filters").inner_text())
        self.assertEqual(self.page.locator("#filters img").count(), 0)
        self.assertIsNone(self.page.evaluate("window.__injected"))

    def test_event_modal_is_plain_text(self):
        self.page.goto(self.url)
        self.page.locator("#status").get_by_text("加载完成", exact=False).wait_for()
        self.page.locator("#events .entry").first.click()
        self.assertIn(HOSTILE, self.page.locator("#detail-title").inner_text())
        self.assertEqual(self.page.locator("#detail-body img").count(), 0)
        self.assertIsNone(self.page.evaluate("window.__injected"))


if __name__ == "__main__":
    unittest.main()
