import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import ai_art


class FakeResponse:
    def __init__(self, payload=None, data=b""):
        self.payload = payload or {}
        self.content = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeReplicate:
    def __init__(self):
        buf = io.BytesIO()
        Image.new("RGB", (768, 1024), "#203355").save(buf, "WEBP")
        self.image = buf.getvalue()
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse({"status": "succeeded", "output": [
            "https://replicate.delivery/example/football-art.webp"
        ]})

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(data=self.image)


class AiArtTests(unittest.TestCase):
    def test_disabled_by_default_prevents_paid_request(self):
        client = FakeReplicate()
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"ENABLE_AI_ART": "", "REPLICATE_API_TOKEN": ""}):
                with self.assertRaises(RuntimeError):
                    ai_art.generate_illustration({"id": "abc"}, Path(temp) / "out.jpg", client)
        self.assertEqual(client.calls, [])

    def test_opted_in_generates_labeled_ready_background(self):
        client = FakeReplicate()
        item = {"id": "abc", "visual_subject": "Lionel Messi", "category": "PARTIDOS"}
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"ENABLE_AI_ART": "true",
                                         "REPLICATE_API_TOKEN": "fake-token-only-for-test"}):
                result = ai_art.generate_illustration(item, Path(temp) / "ai.jpg", client)
                self.assertTrue(result.exists())
        self.assertEqual(len(client.calls), 2)
        prompt = client.calls[0][1]["json"]["input"]["prompt"]
        self.assertIn("Lionel Messi", prompt)
        self.assertIn("NOT a photograph", prompt)

    def test_rejects_untrusted_model_output_domains(self):
        self.assertFalse(ai_art.safe_output_url("https://attacker.example.net/art.webp"))
        self.assertFalse(ai_art.safe_output_url("http://replicate.delivery/art.webp"))
        self.assertTrue(ai_art.safe_output_url("https://replicate.delivery/a.webp"))


if __name__ == "__main__":
    unittest.main()
