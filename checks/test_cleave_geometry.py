"""Synthetic geometry tests; no camera or controller access."""
import ast
import math
import os
from pathlib import Path
import unittest
import numpy as np

tree=ast.parse((Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text())
namespace={'math':math,'os':os}
names=('measure_cleave','refine_cladding_tip','analyze_cladding')
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'cleaves','exec'),namespace)
measure=namespace['measure_cleave']

def edge(angle=0,tilt=0):
    axis=np.array([math.cos(tilt),math.sin(tilt)])
    normal=np.array([-axis[1],axis[0]])
    t=np.linspace(-16,16,29)
    points=np.array([100,100])+t[:,None]*normal+(math.tan(math.radians(angle))*t)[:,None]*axis
    return points,{'m':math.tan(tilt),'diameter_px':40/math.cos(tilt)}

class CleaveTests(unittest.TestCase):
    def test_perfect_perpendicular(self):
        r=measure(*edge())
        self.assertTrue(r['valid'])
        for key in ('angle_error_deg','rms_px','max_deviation_px'):
            self.assertAlmostEqual(r[key],0,places=10)

    def test_beveled_straight_edge(self):
        r=measure(*edge(12))
        self.assertAlmostEqual(r['angle_error_deg'],12,places=8)
        self.assertAlmostEqual(r['rms_px'],0,places=8)

    def test_fiber_tilt_does_not_become_cleave_error(self):
        r=measure(*edge(-7,.2))
        self.assertAlmostEqual(r['angle_error_deg'],-7,places=8)

    def test_defect_is_retained(self):
        points,line=edge();points[14,0]+=6
        r=measure(points,line)
        self.assertGreater(r['rms_px'],1)
        self.assertGreater(r['max_deviation_px'],5)

    def test_missing_or_unresolved_edges(self):
        points,line=edge()
        for bad in ([],points[:7],points[10:19],np.full((29,2),np.nan)):
            self.assertFalse(measure(bad,line)['valid'])

    def test_translation_and_scale(self):
        points,line=edge(8);points[14,0]+=2
        before=measure(points,line)
        after=measure(points*2+30,dict(line,diameter_px=80))
        self.assertAlmostEqual(after['angle_error_deg'],before['angle_error_deg'])
        self.assertAlmostEqual(after['rms_px'],2*before['rms_px'])

    def test_mirror_preserves_error_magnitude(self):
        points,line=edge(8)
        before=measure(points,line)
        points[:,0]*=-1
        after=measure(points,line)
        self.assertAlmostEqual(after['angle_error_deg'],-before['angle_error_deg'])

    def test_real_detector_pipeline(self):
        from PIL import Image
        image=np.full((240,400),220,dtype=np.uint8)
        image[100:140,:140]=30
        image[100:140,240:]=30
        result=namespace['analyze_cladding'](Image.fromarray(image))
        self.assertTrue(result['valid'],result.get('reason'))
        for side in ('left','right'):
            self.assertTrue(result['cleaves'][side]['valid'])
            self.assertAlmostEqual(result['cleaves'][side]['rms_px'],0,places=6)

if __name__=='__main__':unittest.main()
