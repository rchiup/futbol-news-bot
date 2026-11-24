import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import ai_art


def png_bytes(size=(864, 1080)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "#203355").save(buffer, "PNG")
    return buffer.getvalue()


class Response:
    def __init__(self, payload=None, image=b"", status=200, ctype="application/json"):
        self._payload = payload or {}
        self.content = image
        self.status_code = status
        self.headers = {"content-type": ctype}

    def json(self):
        return self._payload


class Session:
    def __init__(self, cf_response=None, hf_response=None, poll_response=None):
        self.cf_response = cf_response
        self.hf_response = hf_response
        self.poll_response = poll_response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if "cloudflare.com" in url:
            return self.cf_response
        return self.hf_response

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.poll_response


class AiArtTests(unittest.TestCase):
    def setUp(self):
        self.item = {"id": "abc", "visual_subject": "Lionel Messi", "sport": "FUTBOL"}
        self.credentials = {"CF_ACCOUNT_ID": "a" * 32, "CF_API_TOKEN": "test"}
        self.cf_ok = Response({"success": True, "result": {
            "image": base64.b64encode(png_bytes()).decode("ascii")}})

    def test_disable_prevents_network_call(self):
        client = Session(cf_response=self.cf_ok)
        with patch.dict(os.environ, {**self.credentials, "ENABLE_AI_ART": "",
                                     "ENABLE_POLLINATIONS": "false"}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(RuntimeError):
                    ai_art.generate_illustration(self.item, Path(directory) / "out.jpg", client)
        self.assertEqual(client.calls, [])

    def test_cloudflare_base64_generates_4x5_jpeg(self):
        client = Session(cf_response=self.cf_ok)
        with patch.dict(os.environ, {**self.credentials, "ENABLE_AI_ART": "true",
                                     "ENABLE_POLLINATIONS": "false"}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "art.jpg"
                result = ai_art.generate_illustration(self.item, path, client)
                self.assertEqual(result, path)
                with Image.open(path) as image:
                    self.assertEqual(image.format, "JPEG")
                    self.assertEqual(image.size, (864, 1080))
        self.assertEqual(self.item["ai_art_provider"], "cloudflare")
        self.assertIn("NOT a documentary photograph", client.calls[0][2]["json"]["prompt"])
        self.assertIn("No people", client.calls[0][2]["json"]["prompt"])

    def test_sinner_background_is_tennis_without_fake_people(self):
        prompt = ai_art.build_prompt({"title":"Sinner se opera y arriesga Australian Open","sport":"FUTBOL"})
        self.assertIn("empty tennis court", prompt)
        self.assertIn("No people", prompt)
        self.assertNotIn("Jannik Sinner", prompt)

    def test_cloudflare_binary_supported(self):
        client = Session(cf_response=Response(image=png_bytes(), ctype="image/png"))
        with patch.dict(os.environ, {**self.credentials, "ENABLE_AI_ART": "true"}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                self.assertTrue(ai_art.generate_illustration(
                    self.item, Path(directory) / "out.jpg", client).exists())

    def test_min_resolution_rejected(self):
        client = Session(cf_response=Response({"result": {
            "image": base64.b64encode(png_bytes((320, 400))).decode("ascii")}}))
        with patch.dict(os.environ, {**self.credentials, "ENABLE_AI_ART": "true"}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(RuntimeError):
                    ai_art.generate_illustration(self.item, Path(directory) / "out.jpg", client)

    def test_cloudflare_failure_falls_back_to_opted_in_pollinations(self):
        client = Session(cf_response=Response(status=429),
                         poll_response=Response(image=png_bytes(), ctype="image/png"))
        with patch.dict(os.environ, {**self.credentials, "ENABLE_AI_ART": "true",
                                     "ENABLE_POLLINATIONS": "true"}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                ai_art.generate_illustration(self.item, Path(directory) / "art.jpg", client)
        self.assertEqual(self.item["ai_art_provider"], "pollinations")
        self.assertEqual(len(client.calls), 2)

    def test_huggingface_off_by_default(self):
        with patch.dict(os.environ, {"HF_TOKEN": "test", "ENABLE_POLLINATIONS": "false"}, clear=True):
            self.assertFalse(ai_art.ai_image_provider_configured())

    def test_huggingface_explicit_opt_in_binary(self):
        client = Session(hf_response=Response(image=png_bytes(), ctype="image/png"))
        with patch.dict(os.environ, {"HF_TOKEN": "test", "ENABLE_AI_ART": "true",
                                     "ENABLE_HF_IMAGE": "true",
                                     "AI_IMAGE_PROVIDER_ORDER": "huggingface"}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                ai_art.generate_illustration(self.item, Path(directory) / "art.jpg", client)
        self.assertEqual(self.item["ai_art_provider"], "huggingface")

    def test_no_provider_is_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ai_art.ai_image_provider_configured())


if __name__ == "__main__":
    unittest.main()
