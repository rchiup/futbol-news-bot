import unittest
from unittest.mock import patch

import insights_probe


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def json(self):
        return self.body


class FakeMetaSession:
    def __init__(self, deny_insights=False):
        self.calls = []
        self.deny_insights = deny_insights

    def get(self, url, params, headers, timeout):
        self.calls.append((url, params, headers))
        if url.endswith("/123") and "fields" in params:
            return Resp(200, {"id": "123", "username": "chaofelicevich",
                              "followers_count": 33, "media_count": 12})
        if url.endswith("/123/media"):
            return Resp(200, {"data": [{"id": "456", "media_type": "IMAGE",
                                      "media_product_type": "FEED",
                                      "timestamp": "2026-11-23T00:00:00+0000"}]})
        if url.endswith("/insights"):
            if self.deny_insights:
                return Resp(400, {"error": {"message": "do not expose this",
                                            "code": 200, "type": "OAuthException"}})
            return Resp(200, {"data": [{
                "name": params["metric"], "values": [{"value": 17}]
            }]})
        raise AssertionError("Unknown URL: " + url)


class InstagramInsightsTests(unittest.TestCase):
    def test_read_only_successfully_reads_meta_and_no_mutations(self):
        fake = FakeMetaSession()
        with patch.dict("os.environ", {
            "IG_USER_ID": "123", "IG_ACCESS_TOKEN": "test-secret",
            "META_GRAPH_VERSION": "v27.0", "META_AUTH_MODE": "facebook",
        }):
            result = insights_probe.probe(session=fake)
        self.assertEqual(result["conclusion"], "insights_accessible")
        self.assertEqual(result["account"]["followers_count"], 33)
        self.assertEqual(result["media_insights"]["shares"]["value"], 17)
        self.assertNotIn("test-secret", str(result))
        self.assertEqual(len(fake.calls), 13)

    def test_permission_denial_is_redacted(self):
        fake = FakeMetaSession(deny_insights=True)
        with patch.dict("os.environ", {
            "IG_USER_ID": "123", "IG_ACCESS_TOKEN": "test-secret",
            "META_GRAPH_VERSION": "v27.0", "META_AUTH_MODE": "facebook",
        }):
            result = insights_probe.probe(session=fake)
        self.assertEqual(result["conclusion"], "insights_permission_or_metric_unavailable")
        self.assertEqual(result["account_insights"]["reach"]["meta_code"], 200)
        self.assertNotIn("do not expose this", str(result))
        self.assertNotIn("test-secret", str(result))

    def test_missing_secret_stops_before_requests(self):
        fake = FakeMetaSession()
        with patch.dict("os.environ", {
            "IG_USER_ID": "", "IG_ACCESS_TOKEN": "",
        }):
            result = insights_probe.probe(session=fake)
        self.assertEqual(result["conclusion"], "missing_secrets")
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
