import tempfile
import unittest
from pathlib import Path

from PIL import Image

from graphics import render_card, fit_lines, font


class GraphicTests(unittest.TestCase):
    def test_all_editorial_categories_generate_instagram_4_by_5(self):
        for category in ("FICHAJES", "PARTIDOS", "SELECCIONES", "LESIONES", "ACTUALIDAD"):
            with self.subTest(category=category):
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "preview.jpg"
                    render_card({
                        "id": "sample-2026",
                        "category": category,
                        "source": "Olé Argentina",
                        "headline": "El fútbol sudamericano vivió una noche inolvidable",
                    }, brand="CHAO FELICEVICH", destination=path)
                    with Image.open(path) as img:
                        self.assertEqual(img.size, (1080, 1350))
                        self.assertEqual(img.format, "JPEG")

    def test_unusually_long_rss_title_does_not_crash_renderer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long-title.jpg"
            render_card({
                "id": "too-long",
                "category": "ACTUALIDAD",
                "source": "The Guardian",
                "title": "Breaking football article about a football club and its future " * 14,
            }, destination=path)
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
