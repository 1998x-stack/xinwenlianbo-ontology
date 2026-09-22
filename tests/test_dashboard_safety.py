"""Static safety checks for the self-contained GitHub Pages dashboard."""

import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[1] / "visualize" / "index.html"


class InlineScript(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not dict(attrs).get("src"):
            self.in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)


class DashboardSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markup = DASHBOARD.read_text(encoding="utf-8")
        parser = InlineScript()
        parser.feed(cls.markup)
        cls.javascript = "\n".join(parser.scripts)

    def test_no_dynamic_html_interpolation_sinks(self):
        for dangerous in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write("):
            with self.subTest(sink=dangerous):
                self.assertNotIn(dangerous, self.javascript)
        self.assertIn("item.textContent = String(value)", self.javascript)
        self.assertIn("$('detail-title').textContent = text(title)", self.javascript)

    def test_external_link_protocol_is_allowlisted(self):
        self.assertIn("url.protocol === 'https:' || url.protocol === 'http:'", self.javascript)
        self.assertIn("link.rel = 'noopener noreferrer'", self.javascript)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_inline_javascript_parses(self):
        result = subprocess.run(
            ["node", "--check"], input=self.javascript,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
