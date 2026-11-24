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

    def test_new_sports_have_distinct_categories(self):
        for sport in ("TENIS", "GOLF", "F1", "NBA"):
            self.assertEqual(editorial.category_for("Player wins championship", sport), sport)
        self.assertEqual(editorial.category_for("Arsenal wins", "FUTBOL"), "ACTUALIDAD")
        self.assertNotIn("nba", editorial.BLOCKED_TOPICS)
        self.assertNotIn("formula 1", editorial.BLOCKED_TOPICS)

    def test_news_sources_include_all_five_sports(self):
        sports = {src.get("sport", "FUTBOL") for src in editorial.FEEDS if isinstance(src, dict)}
        self.assertTrue({"FUTBOL", "TENIS", "GOLF", "F1", "NBA"}.issubset(sports))

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
                 patch.dict(os.environ, {"OPENAI_API_KEY": "", "GROQ_API_KEY": "", "ENABLE_PUBLISH": "", "AUTO_APPROVE": ""}):
                result = editorial.run(self.reference, FakeSession(rss_fixture(self.reference)))
                self.assertEqual(result["queued_new"], 1)
                self.assertEqual(result["published"], 0)
                self.assertTrue(list(previews.glob("*.jpg")))
                queue = editorial.load_queue()
                self.assertEqual(queue[0]["status"], "awaiting_ai")
                editorial.run(self.reference, FakeSession(rss_fixture(self.reference)))
                self.assertEqual(len(editorial.load_queue()), 1)


    def test_no_relevant_photo_never_publishes_blank_card(self):
        """Preview fallback stays available but not published to Instagram."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            queue_path = root / "data" / "queue.json"
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "id": "fifa-without-relevant-photo",
                "title": "FIFA confirma la sede del Mundial Femenino 2035",
                "headline": "FIFA confirma al Reino Unido como sede del Mundial Femenino",
                "description": "La FIFA anunció al Reino Unido como sede del torneo en 2035.",
                "source_url": "https://news.example.org/fifa-2035",
                "status": "draft", "score": 34, "sport": "FUTBOL",
                "category": "SELECCIONES",
                "published_at": self.reference.isoformat(),
                "caption": "La FIFA confirmó la sede para el Mundial Femenino.",
            }
            with patch.object(editorial, "ROOT", root), \
                 patch.object(editorial, "QUEUE", queue_path), \
                 patch.object(editorial, "PREVIEWS", root / "previews"), \
                 patch.object(editorial, "fetch_candidates", return_value=[]), \
                 patch.object(editorial, "make_card") as make, \
                 patch("publisher.available_instagram_slots", return_value=3), \
                 patch("publisher.publish_image") as publish, \
                 patch.dict(os.environ, {
                     "IG_USER_ID": "fake", "IG_ACCESS_TOKEN": "fake",
                     "CLOUDINARY_CLOUD_NAME": "fake",
                     "CLOUDINARY_API_KEY": "fake",
                     "CLOUDINARY_API_SECRET": "fake",
                     "ENABLE_PUBLISH": "true", "AUTO_APPROVE": "true",
                     "GROQ_API_KEY": "", "OPENAI_API_KEY": "",
                     "ENABLE_AI_ART": "false",
                 }):
                editorial.save_queue([entry])
                def render_without_photo(item, **kwargs):
                    item["photo_used"] = False
                    item["ai_art_used"] = False
                    return root / "preview.jpg"
                make.side_effect = render_without_photo
                publish.return_value = "test-media-id"
                result = editorial.run(reference=self.reference)
                self.assertEqual(result["published"], 0)
                publish.assert_not_called()
                held = editorial.load_queue()
                self.assertEqual(held[0]["status"], "needs_review")
                self.assertEqual(held[0]["visual_mode"], "original_graphic")
                self.assertEqual(held[0]["photo_deferred_reason"], "no_relevant_photo")
                self.assertEqual(result["no_photo_deferred"], 1)
                make.reset_mock()
                publish.reset_mock()
                second = editorial.run(reference=self.reference)
                self.assertEqual(second["published"], 0)
                self.assertEqual(second["no_photo_deferred"], 1)
                make.assert_called()
                publish.assert_not_called()
                self.assertEqual(editorial.load_queue()[0]["photo_deferred_reason"], "no_relevant_photo")

    def test_unnamed_18_player_list_is_not_auto_published(self):
        entry = {
            "title": "Which Premier League players face yellow card suspension?",
            "description": "Eighteen players are on the brink of a one-match ban.",
            "headline": "18 jugadores de Premier League al borde de suspensión",
            "visual_subject": "",
        }
        self.assertTrue(editorial.news_missing_critical_details(entry))

    def test_vague_musiala_opinion_is_held(self):
        entry = {
            "title": "Jamal Musiala controversy the nadir of Bayern's turbulent week",
            "description": "Treatment of midfielder raised questions about club reputation.",
            "headline": "Controversia de Musiala marca bajón del Bayern",
            "visual_subject": "Jamal Musiala",
        }
        self.assertTrue(editorial.news_missing_critical_details(entry))

    def test_specific_player_report_is_not_held(self):
        entry = {
            "title": "Lamine Yamal ruled out with ankle injury",
            "description": "Barcelona confirm Lamine Yamal will miss two league games with ankle pain.",
            "headline": "Lamine Yamal se pierde dos partidos por molestias",
            "visual_subject": "Lamine Yamal",
        }
        self.assertFalse(editorial.news_missing_critical_details(entry))

    def test_curated_musiala_photo_is_verified(self):
        from curated_portraits import pick_curated
        info = pick_curated("Jamal Musiala", "Jamal Musiala undergoes treatment at Bayern")
        self.assertIsNotNone(info)
        self.assertEqual(info["photographer"], "Bryan Berlin / WikiPortraits")
        self.assertTrue(info["image_url"].startswith("https://upload.wikimedia.org/"))

    def test_brentford_empty_tactical_preview_is_rejected(self):
        item = {
            "title": "Brentford v Everton: Premier League – live",
            "headline": "Brentford intentará atacar por bandas a Everton",
            "caption": "Brentford buscará presionar y atacar por las bandas.",
        }
        self.assertTrue(editorial.low_value_match_preview(item))

    def test_brentford_actual_result_is_allowed(self):
        item = {
            "title": "Lewis-Potter double and Janelt stunner ease Brentford past Everton",
            "headline": "Brentford vence a Everton con doblete de Lewis-Potter",
            "caption": "Brentford derrotó a Everton 3-1 con dos goles de Lewis-Potter.",
        }
        self.assertFalse(editorial.low_value_match_preview(item))

    def test_actual_live_match_score_is_allowed(self):
        item = {
            "title": "Brentford v Everton: Premier League – live",
            "headline": "Brentford gana 3-1 a Everton",
            "caption": "Brentford ganó 3-1 ante Everton.",
        }
        self.assertFalse(editorial.low_value_match_preview(item))

    def test_untranslated_english_headline_is_rejected(self):
        self.assertTrue(editorial.headline_needs_translation(
            "Chelsea forward victim of robbery after defeat"))
        self.assertFalse(editorial.headline_needs_translation(
            "Chelsea: delantero sufre un robo tras derrota"))

    def test_quarter_hourly_schedule_allows_multiple_posts_with_daily_cap(self):
        from zoneinfo import ZoneInfo
        local = ZoneInfo("America/Santiago")
        slots = [
            datetime(2026, 11, 23, hour, minute, tzinfo=local).astimezone(timezone.utc)
            for hour in range(24)
            for minute in (7, 22, 37, 52)
        ]
        caps = [editorial.morning_burst_settings(at, [])[0] for at in slots]
        self.assertEqual(len(caps), 96)
        self.assertEqual(caps.count(3), 56)
        self.assertEqual(caps.count(2), 40)
        self.assertLessEqual(editorial.POSTS_PER_DAY, 80)
        self.assertEqual(editorial.morning_burst_settings(slots[0], [])[0], 2)
        self.assertEqual(editorial.morning_burst_settings(
            datetime(2026, 11, 23, 9, 7, tzinfo=local).astimezone(timezone.utc), [])[0], 3)

    def test_rendering_without_optional_ai_secret_does_not_generate_art(self):
        with tempfile.TemporaryDirectory() as temp:
            item = {"id": "no-art", "title": "Arsenal win football match", "category": "PARTIDOS"}
            with patch.object(editorial, "PREVIEWS", Path(temp)), \
                 patch.dict(os.environ, {"ENABLE_AI_ART": "false", "REPLICATE_API_TOKEN": ""}), \
                 patch.object(editorial, "generate_illustration") as gen:
                path = editorial.make_card(item, allow_ai=True)
                gen.assert_not_called()
                self.assertFalse(item["ai_art_used"])
                self.assertTrue(path.exists())

    def test_overnight_posts_do_not_use_up_morning_slots(self):
        from zoneinfo import ZoneInfo
        local = ZoneInfo("America/Santiago")
        current = datetime(2026, 11, 23, 8, 20, tzinfo=local).astimezone(timezone.utc)
        posts = [
            {"posted_at": datetime(2026, 11, 23, 1, 20, tzinfo=local).astimezone(timezone.utc).isoformat()},
            {"posted_at": datetime(2026, 11, 23, 6, 50, tzinfo=local).astimezone(timezone.utc).isoformat()},
            {"posted_at": datetime(2026, 11, 23, 7, 10, tzinfo=local).astimezone(timezone.utc).isoformat()},
        ]
        self.assertEqual(editorial.segment_post_count(posts, current, 0, 6), 2)
        self.assertEqual(editorial.segment_post_count(posts, current, 7, 11), 1)
        self.assertEqual(editorial.today_count(posts, "posted_at", current), 3)

    def test_rolling_24_hour_limit_crosses_midnight(self):
        reference = datetime(2026, 11, 23, 5, tzinfo=timezone.utc)
        queue = [
            {"posted_at": (reference - timedelta(hours=2)).isoformat()},
            {"posted_at": (reference - timedelta(hours=20)).isoformat()},
            {"posted_at": (reference - timedelta(hours=26)).isoformat()},
        ]
        self.assertEqual(editorial.rolling_post_count(queue, reference), 2)

    def test_caption_never_ends_mid_sentence(self):
        long_caption = ("River Plate ganó 2-0 y avanzó a cuartos. "
                        "El equipo resolvió el partido con dos goles tras el descanso. "
                        + "Esto no debe publicarse incompleto y sin puntuación " * 12)
        clean = editorial.fit_caption(long_caption)
        self.assertLessEqual(len(clean), 360)
        self.assertTrue(clean.endswith("."))

    def test_caption_raises_without_complete_sentence_to_preserve_clarity(self):
        with self.assertRaises(ValueError):
            editorial.fit_caption("palabras " * 65)

    def test_caption_has_no_source_credit_or_url(self):
        original = "¡Qué partidazo! ¿Quién fue la figura? ⚽\n\nFuente: BBC Sport\nhttps://example.com/news"
        clean = editorial.clean_public_caption(original)
        self.assertEqual(clean, "¡Qué partidazo! ¿Quién fue la figura? ⚽")
        self.assertNotIn("BBC Sport", clean)
        self.assertNotIn("http", clean)

    def test_groq_primary_uses_groq_endpoint_and_model(self):
        item = {"title": "Arsenal win important Champions League match",
                "description": "Arsenal secured a victory.",
                "source": "Example Sports", "published_at": "2026-11-22T18:00:00+00:00"}

        class MockAIResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content":
                        '{"headline":"Arsenal ganó un partido importante",'
                        '"caption":"El Arsenal consiguió una victoria importante."}'}}]}

        class MockAI:
            def __init__(self):
                self.called = None

            def post(self, url, **kwargs):
                self.called = (url, kwargs)
                return MockAIResponse()

        client = MockAI()
        with tempfile.TemporaryDirectory() as temp,              patch.object(editorial, "ROOT", Path(temp)),              patch.dict(os.environ, {"GROQ_API_KEY": "testing-groq-secret",
                                     "GEMINI_API_KEY": "", "CEREBRAS_API_KEY": "",
                                     "OPENROUTER_API_KEY": "",
                                     "OPENAI_API_KEY": "testing-openai-secret"}):
            headline, caption = editorial.draft_with_ai(item, session=client)
        self.assertEqual(headline, "Arsenal ganó un partido importante")
        self.assertTrue(caption.startswith("El Arsenal"))
        self.assertEqual(client.called[0], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(client.called[1]["json"]["model"], "openai/gpt-oss-120b")
        self.assertEqual(client.called[1]["headers"]["Authorization"],
                         "Bearer testing-groq-secret")

    def test_paid_openai_secret_is_never_used_as_fallback(self):
        item = {"title": "Arsenal win important match",
                "description": "Arsenal secured a victory.",
                "source": "Example", "published_at": "2026-11-22T18:00:00+00:00"}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(editorial, "ROOT", Path(temp)), \
             patch.dict(os.environ, {
                 "GROQ_API_KEY": "", "GEMINI_API_KEY": "",
                 "CEREBRAS_API_KEY": "", "OPENROUTER_API_KEY": "",
                 "OPENAI_API_KEY": "a-paid-key-that-must-never-be-called",
             }):
            self.assertIsNone(editorial.draft_with_ai(item))
            self.assertNotIn("llm_provider", item)


if __name__ == "__main__":
    unittest.main()
