import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
import tennis_scorecards as tennis

class TennisScorecardsTest(unittest.TestCase):
    def fixture(self):
        return {"events":[{"name":"Example Open","groupings":[{"name":"Men's Singles","competitions":[{"id":"example","date":"2026-11-24T16:00:00Z","status":{"type":{"name":"STATUS_FINAL","completed":True}},"competitors":[{"athlete":{"displayName":"Carlos Alcaraz"},"winner":True,"linescores":[{"value":6},{"value":4},{"value":7}]},{"athlete":{"displayName":"Jannik Sinner"},"winner":False,"linescores":[{"value":4},{"value":6},{"value":6}]}]}]}]}]}
    def test_final_and_render(self):
        matches=tennis.parse(self.fixture(),datetime(2026,11,24,20,tzinfo=timezone.utc),"atp")
        self.assertEqual(len(matches),1)
        self.assertIn("6-4 4-6 7-6",matches[0]["caption"])
        self.assertEqual(matches[0]["id"],"tennis-atp-example")
        with TemporaryDirectory() as tmp:
            p=tennis.render(matches[0],Path(tmp)/"preview.jpg","CHAO FELICEVICH")
            with Image.open(p) as im:
                self.assertEqual(im.size,(1080,1350))
    def test_no_live_or_old_results(self):
        payload=self.fixture()
        self.assertEqual(tennis.parse(payload,datetime(2026,11,25,tzinfo=timezone.utc),"atp"),[])
        payload["events"][0]["groupings"][0]["competitions"][0]["status"]["type"]={"name":"STATUS_IN_PROGRESS","completed":False}
        self.assertEqual(tennis.parse(payload,datetime(2026,11,24,tzinfo=timezone.utc),"atp"),[])
    def test_chilean_names(self):
        self.assertTrue(tennis.notable({"athlete":{"displayName":"Cristian Garín"}}))
        self.assertFalse(tennis.notable({"athlete":{"displayName":"Unknown Player"}}))
