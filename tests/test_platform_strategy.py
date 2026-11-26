import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import platform_strategy as s
import publisher
import reels

class PlatformStrategyTests(unittest.TestCase):
    def setUp(self):
        self.item={"id":"sample","headline":"El VAR cambia el resultado del partido","caption":"El árbitro revisó el penal en el VAR. La decisión llegó en el último minuto del partido.","sport":"FUTBOL"}
    def test_platform_caption(self):
        self.assertIn("¿Te parece correcta",s.instagram_caption(self.item,self.item["caption"]))
        self.assertIn("#Futbol",s.crosspost_caption(self.item,self.item["caption"],"tiktok"))
        self.assertEqual(s.crosspost_caption(self.item,self.item["caption"],"youtube"),self.item["caption"])
    def test_sensitive(self):
        item={**self.item,"caption":"El jugador sufrió una lesión. El árbitro revisó el penal."}
        self.assertFalse(s.debate_question(item))
        self.assertFalse(s.carousel_detail(item))
    def test_script_grounded(self):
        with patch.object(s,"variant",return_value="headline_hook"):
            script=s.video_script(self.item)
            self.assertTrue(script.startswith(self.item["headline"]))
            self.assertTrue(script.endswith(self.item["caption"]))
            self.assertEqual(" ".join(reels.narration({**self.item,"video_style":"tiktok"})),script)
    def test_carousel_detail(self):
        self.assertEqual(s.carousel_detail(self.item),"La decisión llegó en el último minuto del partido.")
    def test_carousel_publish(self):
        client=Mock()
        def response(data):
            m=Mock()
            m.json.return_value=data
            return m
        client.post.side_effect=[response({"id":"a"}),response({"id":"b"}),response({"id":"parent"}),response({"id":"published"})]
        client.get.return_value=response({"status_code":"FINISHED"})
        with patch.object(publisher,"verify_instagram_account",return_value={"id":"ig"}),patch.object(publisher,"instagram_api_settings",return_value=("ig","token","","https://graph.example")),patch.object(publisher,"upload_public_image",return_value="https://example.org/photo.jpg"):
            self.assertEqual(publisher.publish_carousel([Path("a.jpg"),Path("b.jpg")],"caption","item",session=client),"published")
        self.assertEqual(client.post.call_args_list[2].kwargs["data"]["children"],"a,b")
        self.assertEqual(client.post.call_args_list[3].kwargs["data"]["creation_id"],"parent")
