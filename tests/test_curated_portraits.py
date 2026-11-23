import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curated_portraits import LIBRARY, pick_curated
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
        self.assertEqual(len(LIBRARY), 12)
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
