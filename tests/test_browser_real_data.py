"""Browser smoke test using the repository's checked-in data snapshot."""

import functools
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@unittest.skipUnless(sync_playwright is not None, "Install playwright for browser tests")
class RealSnapshotBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(ROOT))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/visualize/index.html"

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_tracked_snapshot_loads_and_filters(self):
        page = self.browser.new_page()
        try:
            page.goto(self.url)
            page.locator("#status").get_by_text("加载完成", exact=False).wait_for(timeout=20000)
            self.assertGreater(page.locator("#news .entry").count(), 0)
            self.assertGreater(page.locator("#topics .tile").count(), 0)
            self.assertGreater(page.locator("#dates .entry").count(), 0)
            self.assertIn("不代表实时新闻", page.locator("#coverage").inner_text())
            page.locator("#dates .entry").first.click()
            self.assertGreater(page.locator("#news .entry").count(), 0)
            page.locator("#clear").click()
            page.locator("#news .entry").first.click()
            self.assertTrue(page.locator("#detail").evaluate("item => item.open"))
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
