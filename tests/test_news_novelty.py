import unittest
from datetime import datetime, timedelta, timezone

from news_novelty import same_story, duplicate_reason, story_subjects, novelty_priority


NOW = datetime(2026, 11, 23, 16, 10, tzinfo=timezone.utc)


def story(title, headline="", status="draft", sport="FUTBOL", hours=2, subject="",
          id="article", source_url=None):
    return {
        "id": id, "title": title, "headline": headline,
        "description": "Resumen del partido o la noticia deportiva confirmado por el medio.",
        "visual_subject": subject, "sport": sport,
        "source_url": source_url or f"https://example.test/{id}",
        "status": status, "score": 35,
        "published_at": (NOW - timedelta(hours=hours)).isoformat(),
        **({"posted_at": (NOW - timedelta(hours=hours)).isoformat()}
           if status == "published" else {}),
    }


class NoveltyTests(unittest.TestCase):
    def test_pochettino_three_rewritten_articles_only_one_can_publish(self):
        posted = story("Poch blames circumstances in United loss to Liverpool",
                       "Pochettino culpa a las circunstancias en derrota 4-0",
                       status="published", id="poch-original")
        updated = story("Pochettino endured painful debut defeat vs Liverpool",
                        "Liverpool goleó y complica a Pochettino",
                        id="poch-repeat")
        self.assertTrue(same_story(updated, posted))
        self.assertTrue(duplicate_reason(updated, [posted], NOW))

    def test_doue_injury_two_different_wordings_same_story(self):
        older = story("PSG had best attack but Désiré Doué injury will test Enrique",
                      "Lesiones de Doué ponen a prueba a Enrique",
                      status="published", id="doue-original")
        next_version = story("Desire Doue and Kvaratskhelia ruled out for PSG",
                             "Doué y Kvaratskhelia fuera por lesión",
                             id="doue-rewrite")
        self.assertTrue(same_story(next_version, older))

    def test_yamal_injury_is_new_despite_united_and_psg_posts(self):
        prev = [
            story("Pochettino lost with Manchester United", status="published", id="poch"),
            story("Doue injury forces PSG changes", status="published", id="doue"),
        ]
        yamal = story("Lamine Yamal out of Champions due to right ankle problem",
                      "Lamine Yamal será baja para el Barcelona",
                      subject="Lamine Yamal", id="yamal")
        self.assertFalse(duplicate_reason(yamal, prev, NOW))
        self.assertIn("lamine yamal", story_subjects(yamal))

    def test_same_name_older_than_36h_can_be_another_story(self):
        posted = story("Yamal ankle injury", status="published", hours=45, id="first")
        updated = story("Yamal scores decisive goal", hours=1, id="new")
        self.assertFalse(same_story(updated, posted))

    def test_2035_world_cup_host_different_languages(self):
        a = story("UK confirmed host 2035 Women's World Cup after FIFA meeting",
                  "FIFA confirma al Reino Unido sede del Mundial 2035",
                  status="published", id="fifa-2035")
        b = story("FIFA confirmará Reino Unido para Mundial Femenino 2035",
                  "Reino Unido albergará Mundial 2035", id="repeat-fifa")
        self.assertTrue(same_story(a, b))

    def test_different_sports_or_people_are_not_suppressed(self):
        a = story("Lamine Yamal se pierde Champions", id="yamal")
        b = story("Eduardo Vargas convierte otro gol para Universidad de Chile", id="vargas")
        self.assertFalse(same_story(a, b))
        self.assertFalse(same_story(a, story("Tennis final won by Alcaraz",
                                             sport="TENIS", id="tennis")))

    def test_fresh_breaking_story_outweighs_old_photo_story(self):
        new = story("Lamine Yamal se pierde Champions por lesión", hours=1, id="lamine")
        old = story("Pochettino habló después de perder", hours=10, id="poch")
        self.assertGreater(novelty_priority(new, NOW), novelty_priority(old, NOW))

    def test_never_inject_ai_name_not_in_rss_source(self):
        fake = story("Un club confirma una lesión", id="fake-ai", subject="Lionel Messi")
        self.assertNotIn("lionel messi", story_subjects(fake))


if __name__ == "__main__":
    unittest.main()
