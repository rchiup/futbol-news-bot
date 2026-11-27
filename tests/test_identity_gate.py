import unittest
from quality_gate import identity_error
class IdentityTests(unittest.TestCase):
    def test_zverev(self):
        item={"sport":"TENIS","description":"Alexander Zverev won his singles match against Arthur Fery in the Davis Cup.","headline":"Alejandro Zverev cae con Alemania","caption":"Zverev ganó su partido de singles contra Arthur Fery."}
        self.assertEqual(identity_error(item),"translated_person_name")
        item["headline"]="Alexander Zverev cae con Alemania"
        self.assertEqual(identity_error(item),"individual_win_misrepresented_as_loss")
        item["headline"]="Alemania queda eliminada pese al triunfo de Zverev"
        self.assertEqual(identity_error(item),"")
