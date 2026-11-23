import os
import unittest
from pathlib import Path
from unittest.mock import patch

import publisher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeMeta:
    def __init__(self):
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/media_publish"):
            return FakeResponse({"id": "instagram-post-123"})
        if url.endswith("/media"):
            return FakeResponse({"id": "container-456"})
        raise AssertionError(f"unexpected endpoint: {url}")

    def get(self, url, **kwargs):
        if url.endswith("/me/assigned_instagram_accounts"):
            return FakeResponse({"data": [{"id": "1234567", "username": "chaofelicevich"}]})
        if url.endswith("/1234567"):
            return FakeResponse({"id": "1234567", "username": "chaofelicevich"})
        return FakeResponse({"status_code": "FINISHED"})


class PublisherTests(unittest.TestCase):
    def test_credentials_required(self):
        with patch.dict(os.environ, {"IG_USER_ID": "", "IG_ACCESS_TOKEN": ""}):
            with self.assertRaises(RuntimeError):
                publisher.publish_image(Path("not-used.jpg"), "Test caption", "abc")

    def test_meta_publishing_flow_uses_official_endpoints(self):
        client = FakeMeta()
        with patch.dict(os.environ, {"IG_USER_ID": "1234567", "IG_ACCESS_TOKEN": "fake-token",
                                     "META_GRAPH_VERSION": "v24.0"}):
            with patch.object(publisher, "upload_public_image",
                              return_value="https://res.cloudinary.com/demo/image/upload/test.jpg"):
                post_id = publisher.publish_image(Path("unused.jpg"), "An informative caption", "abc",
                                                  session=client)
        self.assertEqual(post_id, "instagram-post-123")
        self.assertEqual(len(client.posts), 2)
        self.assertTrue(client.posts[0][0].endswith("/1234567/media"))
        self.assertTrue(client.posts[1][0].endswith("/1234567/media_publish"))
        self.assertEqual(client.posts[0][1]["data"]["caption"], "An informative caption")


    def test_can_choose_facebook_login(self):
        client = FakeMeta()
        with patch.dict(os.environ, {"IG_USER_ID": "1234567", "IG_ACCESS_TOKEN": "fake-token",
                                     "META_AUTH_MODE": "facebook",
                                     "META_GRAPH_VERSION": "v24.0"}):
            with patch.object(publisher, "upload_public_image",
                              return_value="https://res.cloudinary.com/demo/test.jpg"):
                publisher.publish_image(Path("unused.jpg"), "Test", "abc", session=client)
        self.assertTrue(client.posts[0][0].startswith("https://graph.facebook.com/"))
        self.assertNotIn("access_token", client.posts[0][1]["data"])

    def test_rotated_user_token_works_without_assigned_accounts(self):
        """Graph user tokens can access the IG profile even with zero assigned accounts."""
        class UserTokenMeta(FakeMeta):
            def get(self, url, **kwargs):
                if url.endswith("/me/assigned_instagram_accounts"):
                    raise AssertionError("Do not gate a valid user token on assigned accounts")
                return super().get(url, **kwargs)
        client = UserTokenMeta()
        with patch.dict(os.environ, {"IG_USER_ID": "1234567",
                                     "IG_ACCESS_TOKEN": "new-user-token",
                                     "META_AUTH_MODE": "facebook",
                                     "EXPECTED_IG_USERNAME": "chaofelicevich",
                                     "META_GRAPH_VERSION": "v27.0"}):
            verified = publisher.verify_instagram_account(session=client)
            self.assertEqual(verified["id"], "1234567")
            with patch.object(publisher, "upload_public_image",
                              return_value="https://res.cloudinary.com/demo/image.jpg"):
                media_id = publisher.publish_image(Path("unused.jpg"), "Foto real", "post",
                                                   session=client)
            self.assertEqual(media_id, "instagram-post-123")
        self.assertEqual(len(client.posts), 2)

    def test_refuses_incorrect_instagram_account(self):
        client = FakeMeta()
        with patch.dict(os.environ, {"IG_USER_ID": "1234567", "IG_ACCESS_TOKEN": "test",
                                     "META_AUTH_MODE": "facebook",
                                     "EXPECTED_IG_USERNAME": "different_account"}):
            with patch.object(publisher, "upload_public_image") as uploader:
                with self.assertRaises(RuntimeError):
                    publisher.publish_image(Path("unused.jpg"), "Test", "abc", session=client)
                uploader.assert_not_called()
        self.assertEqual(len(client.posts), 0)

if __name__ == "__main__":
    unittest.main()
