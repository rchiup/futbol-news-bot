import unittest
from quality_gate import sports_topic
class SportsTopicTests(unittest.TestCase):
    def test_stock(self):
        self.assertFalse(sports_topic({"sport":"FUTBOL","title":"Xtiende: la plataforma chilena con IA que ayuda a liquidar sobrestock sin pérdidas","description":"Solución de inventario para empresas"}))
    def test_sports(self):
        self.assertTrue(sports_topic({"title":"Zverev, Germany out of Davis Cup"}))
        self.assertTrue(sports_topic({"title":"Boca se liberó y el juego fluye con los 11 de memoria"}))
