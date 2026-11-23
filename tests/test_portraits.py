import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from portraits import download_portrait, find_portrait, name_in_story


class FakeResponse:
    def __init__(self, payload=None, content=b""):
        self.payload = payload or {}
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class WikimediaStub:
    def __init__(self, license_name="CC0"):
        self.license_name = license_name

    def get(self, url, **kwargs):
        params = kwargs.get("params", {})
        action = params.get("action")
        if action == "wbsearchentities":
            return FakeResponse({"search": [{
                "id": "Q123", "label": "Lionel Messi",
                "description": "Argentine association football player",
            }]})
        if action == "wbgetentities":
            return FakeResponse({"entities": {"Q123": {"claims": {"P18": [{
                "mainsnak": {"datavalue": {"value": "Lionel_Messi_2022.jpg"}}
            }]}}}})
        if action == "query":
            return FakeResponse({"query": {"pages": {"1": {"imageinfo": [{
                "width": 1600, "height": 1200, "mime": "image/jpeg",
                "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/messi.jpg",
                "extmetadata": {
                    "LicenseShortName": {"value": self.license_name},
                    "Copyrighted": {"value": "False"},
                },
            }]}}}})
        if url.startswith("https://upload.wikimedia.org/"):
            with io.BytesIO() as buffer:
                Image.new("RGB", (620, 780), "#ba4c28").save(buffer, "JPEG")
                return FakeResponse(content=buffer.getvalue())
        raise AssertionError("Unexpected URL " + url)


class PortraitTests(unittest.TestCase):
    def test_exact_article_subject_only(self):
        self.assertTrue(name_in_story("Lionel Messi", "¡Lionel Messi da que hablar!", ""))
        self.assertFalse(name_in_story("Lionel Messi", "Cristiano Ronaldo hace historia", ""))
        self.assertFalse(name_in_story("Messi", "Messi mete un gol", ""))

    def test_cc0_footballer_photo_is_accepted_and_downloads(self):
        client = WikimediaStub()
        photo = find_portrait("Lionel Messi", session=client)
        self.assertEqual(photo["wikidata_id"], "Q123")
        self.assertEqual(photo["license"], "cc0")
        with tempfile.TemporaryDirectory() as temp:
            dest = download_portrait(photo, Path(temp) / "portrait.jpg", session=client)
            with Image.open(dest) as result:
                self.assertGreater(result.width, 400)

    def test_attribution_required_photo_is_rejected(self):
        self.assertIsNone(find_portrait("Lionel Messi", session=WikimediaStub("CC BY-SA 4.0")))

    def test_wrong_person_is_rejected(self):
        self.assertIsNone(find_portrait("Lionel Ronaldo", session=WikimediaStub()))


if __name__ == "__main__":
    unittest.main()
