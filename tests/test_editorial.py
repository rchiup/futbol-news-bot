import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

import editorial


class FakeResponse:
    def __init__(self, body: str):
        self.content = body.encode("utf-8")

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, body: str):
        self.body = body
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return FakeResponse(self.body)


def rss_fixture(reference: datetime, include_date=True):
    pubdate = format_datetime(reference - timedelta(hours=2))
    date_xml = f"<pubDate>{pubdate}</pubDate>" if include_date else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Football Daily</title>
      <item><title>Arsenal win important Champions League match</title>
      <link>https://example.org/arsenal?utm_source=feed</link>{date_xml}
      <description>Arsenal secured victory in the fixture.</description></item>
      <item><title>Arsenal win important Champions League match</title>
      <link>https://example.org/arsenal?utm_source=other</link>{date_xml}</item>
    </channel></rss>"""


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.reference = datetime(2026, 11, 22, 20, tzinfo=timezone.utc)

    def test_freshness_and_url_canonicalization(self):
        with patch.object(editorial, "FEEDS", [{"name": "Example", "url": "https://example.org/rss"}]):
            result = editorial.fetch_candidates(self.reference, FakeSession(rss_fixture(self.reference)))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_url"], "https://example.org/arsenal")
        self.assertGreater(result[0]["score"], 15)

    def test_missing_date_is_excluded(self):
        with patch.object(editorial, "FEEDS", ["https://example.org/rss"]):
            result = editorial.fetch_candidates(self.reference, FakeSession(rss_fixture(self.reference, False)))
        self.assertEqual(result, [])

    def test_old_news_is_excluded(self):
        old_reference = self.reference + timedelta(days=12)
        with patch.object(editorial, "FEEDS", ["https://example.org/rss"]):
            result = editorial.fetch_candidates(old_reference, FakeSession(rss_fixture(self.reference)))
        self.assertEqual(result, [])

    def test_similarity_avoids_duplicates_across_sources(self):
        candidate = {"title": "Arsenal win important Champions League match",
                     "source_url": "https://example.org/other"}
        queue = [{"title": "Arsenal win important Champions League match",
                  "source_url": "https://news.example.net/arsenal"}]
        self.assertTrue(editorial.is_duplicate(candidate, queue))

    def test_no_secrets_means_preview_only_and_no_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp) / "queue.json"
            previews = Path(tmp) / "previews"
            with patch.object(editorial, "QUEUE", q), \
                 patch.object(editorial, "PREVIEWS", previews), \
                 patch.object(editorial, "FEEDS", ["https://example.org/rss"]), \
                 patch.dict(os.environ, {"OPENAI_API_KEY": "", "ENABLE_PUBLISH": "", "AUTO_APPROVE": ""}):
                result = editorial.run(self.reference, FakeSession(rss_fixture(self.reference)))
                self.assertEqual(result["queued_new"], 1)
                self.assertEqual(result["published"], 0)
                self.assertTrue(list(previews.glob("*.jpg")))
                queue = editorial.load_queue()
                self.assertEqual(queue[0]["status"], "awaiting_ai")
                editorial.run(self.reference, FakeSession(rss_fixture(self.reference)))
                self.assertEqual(len(editorial.load_queue()), 1)


if __name__ == "__main__":
    unittest.main()
