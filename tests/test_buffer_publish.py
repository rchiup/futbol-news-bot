import os
import unittest
from unittest.mock import patch, Mock
import buffer_publish

class BufferPublishTests(unittest.TestCase):
    def test_crosspost_records_acceptance_and_no_duplicate_submission(self):
        client = Mock()
        client.post.return_value.json.return_value = {"data":{"createPost":{"post":{"id":"buffer-123","status":"scheduled"}}}}
        item = {}
        with patch.dict(os.environ,{"BUFFER_API_KEY":"test","BUFFER_TIKTOK_CHANNEL_ID":"channel-1"}):
            buffer_publish.crosspost(item,"https://example.com/clip.mp4","Titular deportivo",session=client)
            buffer_publish.crosspost(item,"https://example.com/clip.mp4","Titular deportivo",session=client)
        self.assertEqual(item["buffer_tiktok_id"],"buffer-123")
        self.assertEqual(item["buffer_tiktok_status"],"scheduled")
        self.assertEqual(client.post.call_count,1)
        args, kwargs = client.post.call_args
        self.assertEqual(args[0],"https://api.buffer.com")
        self.assertIn("mode: shareNow",kwargs["json"]["query"])

    def test_missing_credentials_no_request(self):
        client=Mock()
        with patch.dict(os.environ,{"BUFFER_API_KEY":"","BUFFER_TIKTOK_CHANNEL_ID":""}):
            buffer_publish.crosspost({},"https://example.com/clip.mp4","Noticia",session=client)
        client.post.assert_not_called()

    def test_uncertain_submission_does_not_retry(self):
        client=Mock()
        client.post.side_effect=TimeoutError()
        item={}
        with patch.dict(os.environ,{"BUFFER_API_KEY":"test","BUFFER_TIKTOK_CHANNEL_ID":"channel-1"}):
            buffer_publish.crosspost(item,"https://example.com/clip.mp4","Noticia",session=client)
            buffer_publish.crosspost(item,"https://example.com/clip.mp4","Noticia",session=client)
        self.assertEqual(item["buffer_tiktok_status"],"check_required")
        self.assertEqual(client.post.call_count,1)

    def test_auto_discovery_matches_only_the_expected_tiktok(self):
        client=Mock()
        first=Mock()
        first.json.return_value={"data":{"account":{"organizations":[{"id":"org"}]}}}
        second=Mock()
        second.json.return_value={"data":{"channels":[{"id":"wrong","name":"personal","service":"tiktok"},{"id":"correct","name":"@chaofelicevich","service":"tiktok"},{"id":"ig","name":"chaofelicevich","service":"instagram"}]}}
        client.post.side_effect=[first,second]
        with patch.dict(os.environ,{"BUFFER_API_KEY":"test","BUFFER_TIKTOK_CHANNEL_ID":"","BUFFER_TIKTOK_USERNAME":"chaofelicevich"}):
            with patch.object(buffer_publish,"_resolved_channel",None):
                self.assertEqual(buffer_publish.resolve_channel(client),"correct")
                self.assertEqual(buffer_publish.resolve_channel(client),"correct")
        self.assertEqual(client.post.call_count,2)

    def test_recovery_reuses_matching_cloudinary_asset(self):
        client=Mock()
        client.get.return_value.status_code=200
        client.get.return_value.json.return_value={"public_id":"football-news-bot/reels/reel-launch-20261124","secure_url":"https://res.cloudinary.com/example/video/upload/reel.mp4"}
        with patch.dict(os.environ,{"CLOUDINARY_CLOUD_NAME":"example","CLOUDINARY_API_KEY":"test","CLOUDINARY_API_SECRET":"test"}):
            self.assertTrue(buffer_publish.recover_original_video("reel-launch-20261124",client).endswith(".mp4"))
