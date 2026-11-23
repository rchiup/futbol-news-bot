import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from openverse_photos import (
    download_openverse_photo, find_openverse_photo, title_matches_person,
    verified_photo_host,
)
from portraits import photo_attribution


class FakeResponse:
    def __init__(self, payload=None, raw=b""):
        self.payload = payload or {}
        self.content = raw

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSearch:
    def __init__(self, title="Lionel Messi after match",
                 license="by-sa", category="photograph"):
        self.title = title
        self.license = license
        self.category = category

    def get(self, url, **kwargs):
        if url.startswith("https://api.openverse.org"):
            data = {
                "title": self.title, "category": self.category,
                "url": "https://live.staticflickr.com/123/example.jpg",
                "license": self.license, "license_version": "4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "creator": "María Futbolera",
                "foreign_landing_url": "https://www.flickr.com/photos/12345/67890",
                "width": 1600, "height": 1300, "mature": False,
            }
            return FakeResponse({"results": [data]})
        with io.BytesIO() as buffer:
            Image.new("RGB", (800, 1200), "#223344").save(buffer, "JPEG")
            return FakeResponse(raw=buffer.getvalue())


class OpenverseTests(unittest.TestCase):
    def test_flickr_cc_by_sa_photo_can_be_used_with_credit(self):
        fake = FakeSearch()
        photo = find_openverse_photo("Lionel Messi", session=fake)
        self.assertIsNotNone(photo)
        self.assertTrue(photo["share_alike"])
        credit = photo_attribution(photo)
        self.assertIn("María Futbolera", credit)
        with tempfile.TemporaryDirectory() as temp:
            dest = download_openverse_photo(photo, Path(temp) / "photo.jpg", session=fake)
            with Image.open(dest) as im:
                self.assertEqual(im.mode, "RGB")

    def test_no_murals_or_shirts_as_photos(self):
        self.assertFalse(title_matches_person("Lionel Messi mural in Buenos Aires", "Lionel Messi"))
        self.assertFalse(title_matches_person("Lionel Messi jersey", "Lionel Messi"))
        self.assertTrue(title_matches_person("Lionel Messi after match", "Lionel Messi"))

    def test_reject_wrong_person_or_untrusted_hosts(self):
        self.assertIsNone(find_openverse_photo("Lionel Messi", session=FakeSearch(
            title="Cristiano Ronaldo celebrates")))
        self.assertFalse(verified_photo_host("https://evil.example/image.jpg"))
        self.assertFalse(verified_photo_host("http://live.staticflickr.com/1.jpg"))
        self.assertTrue(verified_photo_host("https://live.staticflickr.com/1.jpg"))

    def test_reject_restricted_photo_and_illustration(self):
        self.assertIsNone(find_openverse_photo("Lionel Messi", session=FakeSearch(license="by-nc")))
        self.assertIsNone(find_openverse_photo("Lionel Messi", session=FakeSearch(category="illustration")))


if __name__ == "__main__":
    unittest.main()
