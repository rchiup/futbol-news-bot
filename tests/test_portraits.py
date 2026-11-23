import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from portraits import download_portrait, find_portrait, name_in_story, photo_attribution


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
                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/" if "BY-SA" in self.license_name else "https://creativecommons.org/licenses/by/4.0/"},
                    "Artist": {"value": "<a href='https://example.org'>Juan Fotógrafo</a>"},
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

    def test_share_alike_photo_is_allowed_with_compliant_credit(self):
        photo = find_portrait("Lionel Messi", session=WikimediaStub("CC BY-SA 4.0"))
        self.assertIsNotNone(photo)
        self.assertTrue(photo["credit_required"])
        self.assertTrue(photo["share_alike"])
        credit = photo_attribution(photo)
        self.assertIn("Juan Fotógrafo", credit)
        self.assertIn("licenses/by-sa/4.0", credit)
        self.assertIn("misma licencia CC BY-SA", credit)

    def test_unlicensed_photo_is_rejected(self):
        self.assertIsNone(find_portrait("Lionel Messi", session=WikimediaStub("Copyrighted")))

    def test_cc_by_photo_requires_credit(self):
        photo = find_portrait("Lionel Messi", session=WikimediaStub("CC BY 4.0"))
        self.assertIsNotNone(photo)
        self.assertTrue(photo["credit_required"])
        credit = photo_attribution(photo)
        self.assertIn("Juan Fotógrafo", credit)
        self.assertIn("creativecommons.org/licenses/by/4.0", credit)
        self.assertIn("Wikimedia Commons", credit)

    def test_commons_search_fallback_when_primary_photo_is_restricted(self):
        class AlternativePhoto(WikimediaStub):
            def get(self, url, **kwargs):
                params = kwargs.get("params", {})
                if params.get("list") == "search":
                    return FakeResponse({"query": {"search": [
                        {"title": "File:Lionel Messi official portrait 2026.jpg"},
                        {"title": "File:Unrelated man on pitch.jpg"},
                    ]}})
                if params.get("action") == "query":
                    if "official portrait" in params.get("titles", ""):
                        self.license_name = "CC BY-SA 4.0"
                    else:
                        self.license_name = "Copyrighted"
                return super().get(url, **kwargs)
        photo = find_portrait("Lionel Messi", session=AlternativePhoto())
        self.assertIsNotNone(photo)
        self.assertEqual(photo["commons_filename"], "Lionel Messi official portrait 2026.jpg")
        self.assertTrue(photo["share_alike"])

    def test_static_wikimedia_429_uses_public_only_proxy(self):
        class Wikimedia429:
            def __init__(self):
                self.proxy_requested = False
            def get(self, url, **kwargs):
                if url.startswith("https://upload.wikimedia.org/"):
                    denied = FakeResponse()
                    denied.status_code = 429
                    return denied
                if url.startswith("https://thumb.wikimedia.org/"):
                    denied_thumb = FakeResponse()
                    denied_thumb.status_code = 429
                    return denied_thumb
                if url == "https://wsrv.nl/":
                    self.proxy_requested = True
                    self.assertion = kwargs["params"]["url"]
                    with io.BytesIO() as buf:
                        Image.new("RGB", (750, 900), "#234466").save(buf, "JPEG")
                        return FakeResponse(content=buf.getvalue())
                raise AssertionError("Untrusted photo endpoint requested: " + url)

        client = Wikimedia429()
        info = {
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/a/ac/Gianni_Infantino_-_55062516828.jpg",
        }
        with tempfile.TemporaryDirectory() as folder:
            downloaded = download_portrait(info, Path(folder) / "out.jpg", session=client)
            self.assertTrue(downloaded.exists())
            self.assertTrue(client.proxy_requested)
            self.assertEqual(client.assertion, info["image_url"])

    def test_official_thumbnail_rescues_original_rate_limit(self):
        class ThumbnailFallback:
            def __init__(self):
                self.thumbnail_called = False
                self.proxy_called = False
            def get(self, url, **kwargs):
                if url.startswith("https://upload.wikimedia.org/"):
                    response = FakeResponse()
                    response.status_code = 429
                    return response
                if url.startswith("https://thumb.wikimedia.org/"):
                    self.thumbnail_called = True
                    with io.BytesIO() as buf:
                        Image.new("RGB", (700, 950), "#336677").save(buf, "JPEG")
                        return FakeResponse(content=buf.getvalue())
                if url == "https://wsrv.nl/":
                    self.proxy_called = True
                    raise AssertionError("Proxy should not be needed")
                raise AssertionError("Untrusted download URL " + url)

        client = ThumbnailFallback()
        photo = {
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/a/ac/Gianni_Infantino_-_55062516828.jpg"
        }
        with tempfile.TemporaryDirectory() as folder:
            dest = download_portrait(photo, Path(folder) / "out.jpg", session=client)
            self.assertTrue(dest.exists())
            self.assertTrue(client.thumbnail_called)
            self.assertFalse(client.proxy_called)

    def test_wrong_person_is_rejected(self):
        self.assertIsNone(find_portrait("Lionel Ronaldo", session=WikimediaStub()))


if __name__ == "__main__":
    unittest.main()
