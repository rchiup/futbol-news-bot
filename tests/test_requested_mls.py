import unittest
from datetime import datetime,timezone
from unittest.mock import Mock
import requested_mls
class RequestedMLSTests(unittest.TestCase):
    def test_final_only(self):
        session=Mock()
        comp={"status":{"type":{"completed":False,"state":"in"}},"competitors":[{"team":{"displayName":"Columbus Crew"},"score":"1","winner":True},{"team":{"displayName":"Inter Miami CF"},"score":"0","winner":False}]}
        session.get.return_value.json.return_value={"events":[{"date":"2026-11-28T01:00Z","competitions":[comp]}]}
        now=datetime(2026,11,28,3,30,tzinfo=timezone.utc)
        self.assertIsNone(requested_mls.verified_story(now,session))
        comp["status"]["type"]={"completed":True,"state":"post"}
        self.assertIn("1-0",requested_mls.verified_story(now,session)["caption"])
        comp["competitors"][0]["winner"]=False
        self.assertIsNone(requested_mls.verified_story(now,session))
