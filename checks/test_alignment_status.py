"""Gap closure is separate from lateral alignment; unavailable views take priority."""
import ast
import math
from pathlib import Path
import time
import unittest

source=(Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text()
ns={'math':math,'time':time,'finite_value':lambda v:isinstance(v,(int,float)) and math.isfinite(v)}
for name in ('alignment_defaults','angular_alignment_note','fiber_alignment_status'):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<alignment>','exec'),ns)

def views(x=0,y=0,gap=20):
    return {name:dict(valid=True,source='live',source_stamp=100,offset_px=offset,
        angle_deg=0,gap_px=gap,calibration_at_measurement={'um_per_px':1})
        for name,offset in [('X VIEW',x),('Y VIEW',y)]}

class AlignmentStatusTests(unittest.TestCase):
    def classify(self,measurements,**criteria):
        return ns['fiber_alignment_status'](measurements,criteria,now=101)

    def test_gap_closure_does_not_clear_lateral_error(self):
        for gap in (50,4):
            result=self.classify(views(x=0,y=-5,gap=gap))
            self.assertEqual(result['label'],'Position misaligned')
            self.assertIn('Y -5.00 px outside limit',result['detail'])
            self.assertIn('Limit ±2 px',result['detail'])

    def test_both_offsets_within_limit_can_align(self):
        result=self.classify(views(x=2,y=-2),target_gap_um=20,gap_tolerance_um=1)
        self.assertTrue(result['label'].startswith('Position aligned'))
        result=self.classify(views(),target_gap_um=5)
        self.assertTrue(result['label'].startswith('Lateral position aligned'))
        self.assertIn('outside tolerance',result['detail'])

    def test_invalid_view_not_masked_by_other_offset(self):
        records=views(x=50)
        records['Y VIEW'].update(valid=False,reason='Tips too close to measure')
        result=self.classify(records)
        self.assertEqual(result['label'],'Measurement unavailable')
        self.assertIn('Y: Tips too close',result['detail'])

    def test_stale_view_not_classified_aligned(self):
        records=views();records['Y VIEW']['source_stamp']=90
        result=self.classify(records)
        self.assertEqual(result['label'],'Measurement unavailable')
        self.assertIn('stale',result['detail'])

if __name__=='__main__':unittest.main()
