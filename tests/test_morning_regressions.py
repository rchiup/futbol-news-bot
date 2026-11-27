import unittest
from datetime import datetime, timezone, timedelta
from quality_gate import certainty_error
from delivery_scheduler import due
class MorningRegressionTests(unittest.TestCase):
    def test_qualification(self):
        item={"title":"Argentina quedó a un paso de la clasificación al Mundial de Qatar 2027","headline":"Argentina vence a Bahamas y avanza al Mundial"}
        self.assertEqual(certainty_error(item),"qualification_not_yet_secured")
        item["headline"]="Argentina queda a un paso del Mundial tras vencer a Bahamas"
        self.assertEqual(certainty_error(item),"")
    def test_lineup(self):
        item={"title":"Fabricio Pérez le ganaría la pulseada a Cetré","headline":"Fabricio Pérez será titular en la final de la Libertadores"}
        self.assertEqual(certainty_error(item),"unconfirmed_lineup_as_fact")
    def test_old_transfer(self):
        item={"title":"Liam Delap's struggles","description":"Chelsea sold him to Nottingham Forest last summer","headline":"Liam Delap deja Chelsea y se va a Nottingham Forest"}
        self.assertEqual(certainty_error(item),"historical_transfer_as_current")
    def test_quota_backoff(self):
        now=datetime.now(timezone.utc)
        items=[{"youtube_attempt_at":(now-timedelta(minutes=20)).isoformat(),"buffer_youtube_error":"daily_limit"}]
        self.assertFalse(due(items,"youtube",now))
        self.assertTrue(due(items,"tiktok",now))
        self.assertTrue(due(items,"youtube",now+timedelta(hours=1)))
