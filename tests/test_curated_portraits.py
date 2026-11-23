import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curated_portraits import LIBRARY, pick_curated, generic_football_photo
from portraits import photo_attribution
import editorial


class CuratedPortraitTests(unittest.TestCase):
    def test_real_file_links_and_credits(self):
        messi = pick_curated("", "Messi se prepara para un nuevo partido", "")
        self.assertIsNotNone(messi)
        self.assertIn("/f/fc/Lionel_Messi_Argentina_v_Spain_19_July_2026-222.jpg", messi["image_url"])
        self.assertIn("Bryan Berlin", photo_attribution(messi))
        self.assertTrue(messi["share_alike"])

        infantino = pick_curated("", "Infantino anuncia cambios", "")
        self.assertEqual(infantino["image_url"],
                         "https://upload.wikimedia.org/wikipedia/commons/a/ac/Gianni_Infantino_-_55062516828.jpg")
        self.assertIn("Ricardo Stuckert", photo_attribution(infantino))

    def test_ambiguous_name_does_not_select_someone_else(self):
        self.assertIsNone(pick_curated("", "Ronaldo logró una victoria", ""))
        self.assertIsNone(pick_curated("", "El técnico anuncia nuevo contrato", ""))
        self.assertIsNone(pick_curated("Lionel Messi", "Ronaldo marca", ""))

    def test_major_names_and_local_players(self):
        self.assertEqual(len(LIBRARY), 14)
        for title, expected in (
            ("Haaland marcó un doblete", "Erling Haaland"),
            ("Mbappé fue elegido la figura", "Kylian Mbappé"),
            ("Arturo Vidal habla de Colo-Colo", "Arturo Vidal"),
            ("Alexis Sánchez volvió a entrenar", "Alexis Sánchez"),
            ("Cristiano Ronaldo anotó", "Cristiano Ronaldo"),
            ("Pochettino revisa su equipo", "Mauricio Pochettino"),
            ("Bruno Fernandes renueva", "Bruno Fernandes"),
            ("Thiago Almada anota", "Thiago Almada"),
            ("Desire Doue será operado", "Désiré Doué"),
            ("Cherki asistió", "Rayan Cherki"),
        ):
            with self.subTest(title=title):
                self.assertEqual(pick_curated("", title, "")["subject"], expected)

    def test_nicolas_otamendi_and_leandro_paredes_match_recent_articles(self):
        otamendi = pick_curated("", "Mensaje de Otamendi a los hinchas de River", "")
        self.assertIsNotNone(otamendi)
        self.assertEqual(otamendi["subject"], "Nicolás Otamendi")
        paredes = pick_curated("", "La llegada de Boca", "Paredes encabezó los festejos")
        self.assertIsNotNone(paredes)
        self.assertEqual(paredes["subject"], "Leandro Paredes")
        self.assertIsNone(pick_curated("", "Paredes en una cancha de otro club", ""))

    def test_fallback_is_real_soccer_photo_with_cc_credit(self):
        photo = generic_football_photo()
        self.assertTrue(photo["reference_only"])
        self.assertIn("Football_pitch.jpg", photo["image_url"])
        self.assertIn("LensEye Media", photo_attribution(photo))

    def test_photo_first_publish_makes_photo_and_labels_generic(self):
        with tempfile.TemporaryDirectory() as folder:
            item = {"id": "generic-photo", "title": "Instituto recibe a River",
                    "headline": "Instituto se enfrenta a River", "category": "PARTIDOS"}
            from PIL import Image
            fake = Path(folder) / "mock-photo.jpg"
            Image.new("RGB", (800, 800), "#456633").save(fake)
            with patch.object(editorial, "PREVIEWS", Path(folder)), \
                 patch.object(editorial, "ROOT", Path(folder)), \
                 patch.object(editorial, "download_portrait", return_value=fake), \
                 patch.object(editorial, "find_portrait") as search:
                out = editorial.make_card(item, lookup=True, network_lookup=False)
                self.assertTrue(out.exists())
                self.assertTrue(item["photo_used"])
                self.assertTrue(item["reference_photo_used"])
                self.assertFalse(item["portrait_used"])
                self.assertEqual(item["portrait_info"]["photographer"], "LensEye Media")
                search.assert_not_called()

    def test_draft_preview_must_not_make_network_photo_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            item = {"id": "preview", "title": "Infantino anuncia cambios",
                    "headline": "Infantino anuncia cambios", "category": "ACTUALIDAD"}
            with patch.object(editorial, "PREVIEWS", Path(folder)), \
                 patch.object(editorial, "find_portrait") as wikipedia, \
                 patch.object(editorial, "find_openverse_photo") as openverse, \
                 patch.object(editorial, "download_portrait") as downloader:
                destination = editorial.make_card(item)
                self.assertTrue(destination.exists())
                wikipedia.assert_not_called()
                openverse.assert_not_called()
                downloader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
