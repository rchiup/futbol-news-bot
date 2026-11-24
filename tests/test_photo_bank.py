import unittest
from unittest.mock import patch
import photo_bank

class PhotoBankTests(unittest.TestCase):
    def test_only_source_entities(self):
        result=photo_bank.entities({"title":"Liverpool gana a Arsenal"}, {"personas":["Fake Player"],"clubes":["Liverpool","Chelsea"]})
        self.assertEqual(result["personas"],[])
        self.assertIn("Liverpool",result["clubes"])
        self.assertNotIn("Chelsea",result["clubes"])

    def test_cached_stadium_without_network(self):
        photo={"image_url":"https://upload.wikimedia.org/example.jpg","entity_kind":"club"}
        with patch("photo_bank.load_bank",return_value={"club:liverpool":photo}), patch("photo_bank.find_entity_photo") as lookup:
            self.assertEqual(photo_bank.choose_photo({"title":"Liverpool gana"},network=False),photo)
            lookup.assert_not_called()

    def test_ambiguous_club_does_not_guess_venue(self):
        with patch("photo_bank.resolve",return_value="Q1"),patch("photo_bank.claims_for",return_value={"P115":[{"mainsnak":{"datavalue":{"value":{"id":"Q2"}}}},{"mainsnak":{"datavalue":{"value":{"id":"Q3"}}}}]}):
            self.assertIsNone(photo_bank.find_entity_photo("Liverpool","club"))

if __name__=="__main__":
    unittest.main()
