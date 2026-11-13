import ast
import math
from pathlib import Path
import unittest

tree=ast.parse((Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text())
ns={'math':math}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('optical_loss_db','optical_transmission_percent')],type_ignores=[]),'optical','exec'),ns)

class OpticalLossTests(unittest.TestCase):
    def test_known_losses(self):
        for a,b,want in ((1,1,0),(1,.1,10),(10,1,10),(1,2,-3.01029995664)):
            self.assertAlmostEqual(ns['optical_loss_db'](a,b),want,places=8)

    def test_invalid_readings(self):
        for value in (0,-1,float('nan'),float('inf'),'bad'):
            for pair in ((value,1),(1,value)):
                with self.assertRaises(ValueError):ns['optical_loss_db'](*pair)

    def test_large_valid_values_do_not_overflow_percentage(self):
        self.assertEqual(ns['optical_transmission_percent'](1e308,1e308),100)
        self.assertEqual(ns['optical_transmission_percent'](1e308,5e307),50)

    def test_extreme_ratios_and_gain(self):
        self.assertTrue(math.isfinite(ns['optical_loss_db'](1e308,1e-308)))
        self.assertEqual(ns['optical_transmission_percent'](1e308,1e-308),0)
        self.assertIsNone(ns['optical_transmission_percent'](1e-308,1e308))

if __name__=='__main__':unittest.main()
