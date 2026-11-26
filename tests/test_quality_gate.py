import unittest
from quality_gate import score_error, photo_safe

class QualityGateTests(unittest.TestCase):
    def test_psg_draw_not_defeat(self):
        item={"sport":"FUTBOL","title":"PSG held by Roma","description":"PSG 2-2 Roma","headline":"Luis Enrique analiza el empate","caption":"El PSG cayó 2‑2 ante la Roma."}
        self.assertEqual(score_error(item),"draw_described_as_win_or_loss")
        item["caption"]="El PSG empató 2-2 ante la Roma."
        self.assertEqual(score_error(item),"")
    def test_invented_score(self):
        item={"title":"Bayern loses 2-1","caption":"Bayern perdió 2-0."}
        self.assertEqual(score_error(item),"unverified_numeric_score")
    def test_known_scoreboard(self):
        match={"sport":"FUTBOL","match_result":[{"name":"Paris Saint-Germain","abbr":"PSG","score":2},{"name":"AS Roma","abbr":"ROMA","score":2}]}
        item={"title":"PSG held by Roma","caption":"PSG empató 2-2 ante Roma."}
        self.assertEqual(score_error(item,[match]),"")
    def test_wrong_portrait(self):
        item={"title":"Luis Enrique calls Roma toughest test"}
        info={"subject":"Luis Enrique","wikidata_id":"Q222789","image_url":"https://example.org/image.jpg","commons_filename":"Luis Enrique Ponce, Estadio, 1951-07-28.jpg"}
        self.assertFalse(photo_safe(info,item))
    def test_unrelated_photo(self):
        self.assertFalse(photo_safe({"subject":"Lionel Messi","image_url":"https://example.org/photo.jpg"},{"title":"PSG held by Roma"}))
    def test_valid_photo(self):
        self.assertTrue(photo_safe({"subject":"Lamine Yamal","image_url":"https://example.org/photo.jpg","commons_filename":"Lamine Yamal 2026.jpg"},{"title":"Lamine Yamal returns"}))
