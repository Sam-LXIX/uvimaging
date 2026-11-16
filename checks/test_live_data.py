"""Live camera readouts must not present stale or sample data as measurements."""
import ast
import math
from pathlib import Path
import unittest

tree=ast.parse((Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EngineeringLotusUI')
node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='live_measurement_text')
node.decorator_list=[]
ns={'finite_value':lambda v:isinstance(v,(int,float)) and math.isfinite(v),'MUTED':'muted','TEXT':'text'}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<live-data>','exec'),ns)
format_text=ns['live_measurement_text']

def result(**extra):
    return dict(dict(source='live',source_stamp=100,valid=True,gap_px=10,offset_px=-2,
                     angle_deg=1.5,quality=89,processing_ms=300),**extra)

class LiveDataTests(unittest.TestCase):
    def test_uncalibrated(self):
        text,color=format_text(result(),101)
        self.assertIn('Gap 10.00',text);self.assertIn('Offset -2.00',text)
        self.assertIn('px (uncalibrated)',text);self.assertIn('Tilt +1.50°',text)
        self.assertIn('1.00 s old',text)

    def test_calibrated(self):
        text,_=format_text(result(calibration_at_measurement={'um_per_px':2}),101)
        self.assertIn('Gap 20.00',text);self.assertIn('Offset -4.00 µm',text)

    def test_stale_missing_and_samples(self):
        for r,now in [(result(),103),({},101),(result(source='sample'),101),(result(source_stamp=102),101)]:
            text,_=format_text(r,now)
            self.assertNotIn('Gap 10.00',text);self.assertIn('unavailable',text)

    def test_invalid_detection(self):
        text,_=format_text(result(valid=False,reason='Tip boundary unresolved'),101)
        self.assertIn('Tip boundary unresolved',text);self.assertNotIn('Gap 10.00',text)
