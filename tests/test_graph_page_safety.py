"""Offline static checks for the graph visualizer's DOM trust boundary."""

import shutil
import subprocess
import unittest
from pathlib import Path

from test_dashboard_safety import InlineScript

GRAPH_HTML = Path(__file__).resolve().parents[1] / "visualize" / "graph.html"


class GraphPageSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parser = InlineScript()
        parser.feed(GRAPH_HTML.read_text(encoding="utf-8"))
        cls.javascript = "\n".join(parser.scripts)

    def test_tooltip_and_error_are_plain_text(self):
        for dangerous in ("innerHTML", "outerHTML", "insertAdjacentHTML", ".html(", "document.write("):
            with self.subTest(sink=dangerous):
                self.assertNotIn(dangerous, self.javascript)
        self.assertIn("$('tooltip-label').textContent", self.javascript)
        self.assertIn("$('tooltip-info').textContent", self.javascript)
        self.assertIn("$('notice').textContent", self.javascript)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_inline_javascript_parses(self):
        result = subprocess.run(
            ["node", "--check"], input=self.javascript,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
