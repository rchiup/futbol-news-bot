import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import requests

import free_llm


GOOD = {"headline": "Arsenal consigue una victoria importante en Champions",
        "caption": "El Arsenal ganó su partido y sigue en carrera por la Champions.",
        "visual_subject": ""}
MESSAGES = [{"role": "system", "content": "Solo JSON."},
            {"role": "user", "content": "Arsenal ganó un partido."}]


class FakeResp:
    def __init__(self, data=None, status=200):
        self.value = data or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"Response {self.status_code}")
            err.response = self
            raise err

    def json(self):
        return self.value


class RoutingSession:
    def __init__(self, bad=None):
        self.calls = []
        self.bad = bad or set()

    def post(self, url, headers, json, timeout):
        self.calls.append((url, headers, json))
        if any(tag in url for tag in self.bad):
            return FakeResp(status=429)
        if "generativelanguage.googleapis.com" in url:
            return FakeResp({"candidates": [
                {"content": {"parts": [{"text": __import__("json").dumps(GOOD)}]}}
            ]})
        return FakeResp({"choices": [
            {"message": {"content": __import__("json").dumps(GOOD)}}
        ]})


class FreeLLMTests(unittest.TestCase):
    def setUp(self):
        self.env = {"GROQ_API_KEY": "groq-test", "GEMINI_API_KEY": "gemini-test",
                    "GEMINI_FREE_TIER_CONFIRMED": "true",
                    "CEREBRAS_API_KEY": "cerebras-test",
                    "CEREBRAS_FREE_TIER_CONFIRMED": "true",
                    "OPENROUTER_API_KEY": "router-test",
                    "FREE_LLM_ORDER": "groq,gemini,cerebras,openrouter"}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.usage = Path(self.tmp.name) / "usage.json"

    def test_only_configured_free_models_are_eligible(self):
        env = {**self.env, "OPENAI_API_KEY": "paid-key",
               "GEMINI_FREE_TIER_CONFIRMED": "false",
               "CEREBRAS_FREE_TIER_CONFIRMED": "false"}
        self.assertEqual(free_llm.providers(env), ["groq", "openrouter"])
        self.assertNotIn("openai", free_llm.KEYS)
        self.assertEqual(free_llm.MODELS["openrouter"], "openrouter/free")

    def test_groq_success_tracks_quality_and_latency(self):
        session = RoutingSession()
        output, provider = free_llm.generate(
            MESSAGES, session=session, env=self.env, usage_path=self.usage)
        self.assertEqual(provider, "groq")
        self.assertEqual(output["headline"], GOOD["headline"])
        self.assertIn("/chat/completions", session.calls[0][0])
        stats = free_llm.summary(self.usage)["providers"]["groq"]
        self.assertEqual(stats["success"], 1)
        self.assertGreaterEqual(stats["avg_readability"], 60)

    def test_groq_429_falls_through_to_free_gemini(self):
        session = RoutingSession(bad={"api.groq.com"})
        out, provider = free_llm.generate(
            MESSAGES, session=session, env=self.env, usage_path=self.usage)
        self.assertEqual(provider, "gemini")
        self.assertEqual(out["headline"], GOOD["headline"])
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(session.calls[1][0].endswith(":generateContent"))
        self.assertEqual(free_llm.summary(self.usage)["providers"]["groq"]["failures"], 1)

    def test_gemini_429_falls_through_to_cerebras(self):
        env = {**self.env, "GROQ_API_KEY": ""}
        session = RoutingSession(bad={"generativelanguage.googleapis.com"})
        _, provider = free_llm.generate(MESSAGES, session=session,
                                        env=env, usage_path=self.usage)
        self.assertEqual(provider, "cerebras")

    def test_only_openrouter_free_is_ever_invoked(self):
        env = {**self.env, "GROQ_API_KEY": "", "GEMINI_API_KEY": "",
               "CEREBRAS_API_KEY": "", "OPENROUTER_MODEL": "anthropic/claude-opus-4"}
        session = RoutingSession()
        _, provider = free_llm.generate(MESSAGES, session=session,
                                        env=env, usage_path=self.usage)
        self.assertEqual(provider, "openrouter")
        self.assertEqual(session.calls[0][2]["model"], "openrouter/free")

    def test_exhaustion_returns_error_without_paid_fallback(self):
        session = RoutingSession(bad={"api.groq.com", "generativelanguage.googleapis.com",
                                      "api.cerebras.ai", "openrouter.ai"})
        with self.assertRaisesRegex(ValueError, "Free LLMs unavailable"):
            free_llm.generate(MESSAGES, session=session, env=self.env,
                              usage_path=self.usage)
        self.assertEqual(len(session.calls), 4)
        self.assertNotIn("api.openai.com", str(session.calls))

    def test_local_cap_counts_failed_requests(self):
        env = {**self.env, "GROQ_API_KEY": "", "GEMINI_API_KEY": "",
               "CEREBRAS_API_KEY": ""}
        with patch.dict(free_llm.CAPS, {"openrouter": 1}):
            _, provider = free_llm.generate(MESSAGES, session=RoutingSession(),
                                            env=env, usage_path=self.usage)
            self.assertEqual(provider, "openrouter")
            with self.assertRaisesRegex(ValueError, "Free LLMs unavailable"):
                free_llm.generate(MESSAGES, session=RoutingSession(),
                                  env=env, usage_path=self.usage)
        self.assertEqual(free_llm.summary(self.usage)["providers"]["openrouter"]["attempts"], 1)

    def test_malformed_json_falls_back_to_next_free_provider(self):
        class BadGroq(RoutingSession):
            def post(self, url, headers, json, timeout):
                if "api.groq.com" in url:
                    self.calls.append((url, headers, json))
                    return FakeResp({"choices": [{"message": {"content": "not JSON"}}]})
                return super().post(url, headers, json, timeout)
        session = BadGroq()
        _, provider = free_llm.generate(MESSAGES, session=session,
                                        env=self.env, usage_path=self.usage)
        self.assertEqual(provider, "gemini")

    def test_public_metrics_do_not_contain_access_tokens(self):
        free_llm.generate(MESSAGES, session=RoutingSession(),
                          env=self.env, usage_path=self.usage)
        on_disk = self.usage.read_text(encoding="utf-8")
        for key in ("groq-test", "gemini-test", "router-test", "cerebras-test"):
            self.assertNotIn(key, on_disk)


if __name__ == "__main__":
    unittest.main()
