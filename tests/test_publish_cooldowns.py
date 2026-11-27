import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock
import publish_cooldowns as c
class CooldownTests(unittest.TestCase):
    def tearDown(self):
        c.configure([])
    def test_retry_after_persisted(self):
        queue=[{}]
        c.configure(queue)
        now=datetime.now(timezone.utc)
        self.assertTrue(c.observe("buffer",Mock(status_code=429,headers={"Retry-After":"1800"}),now))
        c.configure(queue)
        self.assertFalse(c.available("buffer",now))
        self.assertTrue(c.available("zernio",now))
        self.assertTrue(c.available("buffer",now+timedelta(minutes=31)))
    def test_non_429(self):
        c.configure([{}])
        self.assertFalse(c.observe("buffer",Mock(status_code=200,headers={}),datetime.now(timezone.utc)))
        self.assertTrue(c.available("buffer"))
