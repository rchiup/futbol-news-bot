import unittest
from unittest.mock import Mock, patch

from google_images import commons_filename_from_url, find_google_image


class GoogleImagesTests(unittest.TestCase):
    def test_commons_url_accepts_exact_named_subject(self):
        self.assertEqual(
            commons_filename_from_url(
                "https://commons.wikimedia.org/wiki/File:Jamal_Musiala_training.jpg",
                "Jamal Musiala",
            ),
            "Jamal Musiala training.jpg",
        )

    def test_wrong_player_is_rejected(self):
        self.assertIsNone(commons_filename_from_url(
            "https://commons.wikimedia.org/wiki/File:Lionel_Messi.jpg",
            "Jamal Musiala",
        ))

    def test_google_is_discovery_and_rights_checked_on_source(self):
        response = Mock()
        response.text = ('<a href="https://commons.wikimedia.org/wiki/'
                         'File:Jamal_Musiala_training.jpg">Photo</a>')
        session = Mock()
        session.get.return_value = response
        checked = {"image_url": "https://upload.wikimedia.org/football.jpg"}
        with patch("google_images._check_commons_file", return_value=checked) as license_check:
            result = find_google_image("Jamal Musiala", session=session)
        self.assertEqual(result["photo_provider"], "Google Images → Wikimedia Commons")
        license_check.assert_called_once()
        self.assertEqual(session.get.call_args.kwargs["params"]["tbm"], "isch")

    def test_unlicensed_result_not_selected(self):
        response = Mock()
        response.text = ('https://commons.wikimedia.org/wiki/'
                         'File:Jamal_Musiala_training.jpg')
        session = Mock()
        session.get.return_value = response
        with patch("google_images._check_commons_file", return_value=None):
            self.assertIsNone(find_google_image("Jamal Musiala", session=session))


if __name__ == "__main__":
    unittest.main()
