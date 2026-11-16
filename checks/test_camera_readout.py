"""Readout rendering preserves units and suppresses stale values."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

source=ast.parse((Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text())
cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='EngineeringLotusUI')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='paint_camera_readout')
ns={'time':SimpleNamespace(monotonic=lambda:101),'finite_value':lambda n:isinstance(n,(int,float)) and math.isfinite(n)}
ns.update({k:k for k in ('WHITE','BORDER','MUTED','PURPLE','FONT')})
exec(compile(ast.Module(body=[method],type_ignores=[]),'<readout>','exec'),ns)

class CameraReadoutTests(unittest.TestCase):
    def render(self,stamp):
        canvas=Mock(readout_result=dict(valid=True,source='live',source_stamp=stamp,
            gap_px=10,offset_px=-2,angle_deg=1.5,quality=89,processing_ms=300,
            calibration_at_measurement={'um_per_px':2}),readout_sample=False)
        canvas.winfo_width.return_value=500
        ui=SimpleNamespace(live_measurement_text=lambda *a:('details','color'))
        with patch('tkinter.font.Font') as font:
            font.return_value.measure.return_value=10
            ns['paint_camera_readout'](ui,canvas)
        return [c.kwargs['text'] for c in canvas.create_text.call_args_list]

    def test_calibrated_values(self):
        text=self.render(100)
        for value in ('20.00 µm','-4.00 µm','+1.50°'):
            self.assertIn(value,text)

    def test_stale_shows_dashes(self):
        text=self.render(90)
        self.assertEqual(text.count('—'),3)
        self.assertIn('WAITING · no recent live measurement',text)
