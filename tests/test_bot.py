import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import bot


class FakeFeed:
    def __init__(self):
        self.bozo = False
        self.feed = {"title": "Test Football"}
        self.entries = [
            {"title": "Club announces transfer", "link": "https://example.org/a"},
            {"title": "Club announces transfer", "link": "https://example.org/a"},
            {"title": "Another result", "link": "https://example.org/b"},
            {"title": "Missing URL"},
        ]


class CollectorTests(unittest.TestCase):
    def test_collect_and_deduplicate_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "news.json"
            with patch.object(bot, "OUT", target), patch.object(bot, "FEEDS", ["https://example.org/rss"]), patch.object(bot.feedparser, "parse", return_value=FakeFeed()):
                bot.main()
                first = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(len(first), 2)
                self.assertTrue(all(item["status"] == "pending_review" for item in first))
                bot.main()
                second = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(len(second), 2)


if __name__ == "__main__":
    unittest.main()
