import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import delivery_scheduler as d
import buffer_publish as b
class DeliveryTests(unittest.TestCase):
    def test_independent_clock(self):
        now=datetime.now(timezone.utc)
        q=[{"youtube_attempt_at":now.isoformat()}]
        self.assertFalse(d.due(q,"youtube",now))
        self.assertTrue(d.due(q,"tiktok",now))
        self.assertTrue(d.due(q,"youtube",now+timedelta(minutes=16)))
    def test_avoid_duplicate(self):
        self.assertFalse(d.pending_platform({"zernio_youtube_status":"check_required"},"youtube"))
        self.assertTrue(d.pending_platform({"zernio_youtube_status":"sent"},"tiktok"))
    def test_quota(self):
        with patch.object(b,"configured",return_value=True),patch.dict("os.environ",{"BUFFER_YOUTUBE_CHANNEL_ID":"channel"}),patch.object(b,"graphql",return_value={"dailyPostingLimits":[{"channelId":"channel","isAtLimit":True}]}):
            self.assertFalse(b.network_has_capacity("youtube"))
    def test_refresh(self):
        item={"buffer_youtube_id":"post","buffer_youtube_status":"sending"}
        with patch.object(b,"configured",return_value=True),patch.object(b,"graphql",return_value={"post":{"id":"post","status":"sent","externalLink":"https://www.youtube.com/shorts/abc"}}):
            b.refresh(item,"youtube")
        self.assertEqual(item["buffer_youtube_status"],"sent")
        self.assertTrue(item["buffer_youtube_url"].endswith("abc"))
    def test_errors(self):
        self.assertEqual(b.classify_error("The daily posting limit for this channel has been reached!"),"daily_limit")
