import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import reels
import publisher
from test_publisher import FakeMeta

class ReelTests(unittest.TestCase):
    def test_narration_is_grounded_and_chunks_match(self):
        item={"headline":"Resultado confirmado","caption":"El equipo ganó el partido por dos goles a uno. El delantero marcó el gol decisivo en la segunda parte.","photo_used":True}
        self.assertTrue(reels.eligible(item))
        self.assertEqual(" ".join(reels.narration(item)),item["caption"])
        self.assertFalse(reels.eligible({**item,"match_result":[1,2]}))
        with tempfile.TemporaryDirectory() as tmp:
            cover=Path(tmp)/"cover.jpg"
            Image.new("RGB",(1080,1350),"navy").save(cover)
            frame=Path(tmp)/"frame.png"
            reels.frame(cover,reels.narration(item)[0],item,0,2,frame,"CHAO FELICEVICH")
            with Image.open(frame) as im:
                self.assertEqual(im.size,(1080,1920))

    def test_reel_meta_flow(self):
        client=FakeMeta()
        with patch.dict(os.environ,{"IG_USER_ID":"1234567","IG_ACCESS_TOKEN":"fake-token","EXPECTED_IG_USERNAME":"chaofelicevich"}):
            with patch.object(publisher,"upload_public_video",return_value="https://res.cloudinary.com/demo/video/upload/test.mp4"):
                result=publisher.publish_reel(Path("test.mp4"),"Noticia","test",session=client)
        self.assertEqual(result,"instagram-post-123")
        data=client.posts[0][1]["data"]
        self.assertEqual(data["media_type"],"REELS")
        self.assertEqual(data["share_to_feed"],"true")
        self.assertTrue(data["video_url"].endswith(".mp4"))
        self.assertEqual(len(client.posts),2)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg not installed")
    def test_real_mp4_encoding(self):
        import wave
        item={"headline":"Resultado confirmado","caption":"El equipo ganó el partido por dos goles a uno. El delantero marcó el gol decisivo en la segunda parte.","photo_used":True}
        def fake_voice(text,path):
            with wave.open(str(path),"wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
                w.writeframes(b"\x00\x00"*44100)
        with tempfile.TemporaryDirectory() as tmp:
            cover=Path(tmp)/"cover.jpg"
            Image.new("RGB",(1080,1350),"navy").save(cover)
            with patch.object(reels,"voice",side_effect=fake_voice):
                output=reels.render(item,cover,Path(tmp)/"reel.mp4","CHAO FELICEVICH")
            self.assertGreater(output.stat().st_size,1000)
