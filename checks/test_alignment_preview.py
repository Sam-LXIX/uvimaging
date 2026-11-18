"""Live motion must remain visible while an older analysis result is displayed."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from PIL import Image

tree=ast.parse((Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EngineeringLotusUI')
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('render_engineering','preview_with_outlines')]
base=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
methods.append(next(n for n in base.body if isinstance(n,ast.FunctionDef) and n.name=='update_camera_views'))
ns={'time':SimpleNamespace(monotonic=lambda:101),
    'math':math,'finite_value':lambda value:isinstance(value,(int,float)) and math.isfinite(value),
    'fiber_alignment_status':lambda *args:dict(label='Measurement unavailable',detail='Check focus',
        views={'X VIEW':'Unavailable','Y VIEW':'Unavailable'}),
    'orient_camera_frame':lambda image,name:image,
    'RED':'red','GREEN':'green','MUTED':'gray'}
exec(compile(ast.Module(body=methods,type_ignores=[]),'<preview>','exec'),ns)

class AlignmentPreviewTests(unittest.TestCase):
    def ui(self):
        canvas=Mock()
        canvas.winfo_exists.return_value=True
        canvas.winfo_width.return_value=100
        canvas.winfo_height.return_value=80
        old=Image.new('RGB',(100,80),'red')
        ui=SimpleNamespace(measurements={'X VIEW':dict(valid=False,source='live',source_stamp=100,
                           reason='Check focus',measured_at='unchanged')},
            alignment_criteria={},alignment_status_label=None,
            engineering_widgets={'X VIEW':(canvas,Mock())},measurement_sources={'X VIEW':old},
            analysis_samples={},camera_order={'X VIEW':0},mask_views={},analysis_masks={},
            outline_views={'X VIEW':False},
            feeds=Mock(),update_camera_readout=Mock(),overlay=Mock(side_effect=lambda image,result:image))
        ui.preview_with_outlines=lambda *args:ns['preview_with_outlines'](ui,*args)
        return ui,canvas

    def render(self,ui):
        with patch('PIL.ImageTk.PhotoImage',side_effect=lambda image,**kwargs:image.copy()):
            ns['render_engineering'](ui)

    def test_new_frames_advance_without_waiting_for_new_measurements(self):
        ui,canvas=self.ui()
        ui.feeds.analysis_snapshot.return_value=(Image.new('RGB',(100,80),'blue'),100.8,'Live')
        self.render(ui)
        self.assertEqual(canvas.photo.getpixel((0,0)),(0,0,255))
        ui.feeds.analysis_snapshot.return_value=(Image.new('RGB',(100,80),'green'),100.9,'Live')
        self.render(ui)
        self.assertEqual(canvas.photo.getpixel((0,0)),(0,128,0))
        ui.overlay.assert_not_called()

    def test_stalled_capture_does_not_keep_showing_old_live_image(self):
        ui,canvas=self.ui()
        ui.feeds.analysis_snapshot.return_value=(Image.new('RGB',(100,80),'blue'),90,'Live')
        self.render(ui)
        canvas.create_image.assert_not_called()
        self.assertEqual(canvas.create_text.call_args.kwargs['text'],'Waiting for a recent camera frame')

    def test_overlay_mode_uses_the_image_that_produced_its_measurements(self):
        ui,canvas=self.ui()
        ui.mask_views['X VIEW']=True
        self.render(ui)
        self.assertEqual(canvas.photo.getpixel((0,0)),(255,0,0))
        ui.overlay.assert_called_once()
        ui.feeds.analysis_snapshot.assert_not_called()

    def test_sample_image_is_not_replaced_by_live_capture(self):
        ui,canvas=self.ui()
        ui.analysis_samples['X VIEW']=ui.measurement_sources['X VIEW']
        ui.measurements['X VIEW']['source']='sample'
        self.render(ui)
        self.assertEqual(canvas.photo.getpixel((0,0)),(255,0,0))
        ui.feeds.analysis_snapshot.assert_not_called()

    def test_alignment_outlines_use_the_matching_analyzed_frame(self):
        ui,canvas=self.ui()
        ui.outline_views['X VIEW']=True
        ui.measurements['X VIEW']['valid']=True
        # Keep measurement rendering independent of this preview-selection check.
        ui.measurements['X VIEW'].update(quality=89,gap_px=10,offset_px=0,angle_deg=0,lines=[])
        ui.feeds.analysis_snapshot.return_value=(Image.new('RGB',(100,80),'blue'),100.9,'Live')
        self.render(ui)
        self.assertEqual(canvas.photo.getpixel((0,0)),(255,0,0))
        ui.overlay.assert_called_once_with(ui.measurement_sources['X VIEW'],ui.measurements['X VIEW'])

    def test_live_view_outlines_and_raw_toggle(self):
        ui,canvas=self.ui()
        ui.outline_views['X VIEW']=True
        ui.measurements['X VIEW']['valid']=True
        ui.closing=False;ui.camera_images={};ui.camera_views={'X VIEW':canvas};ui.after=Mock()
        ui.update_camera_views=lambda:ns['update_camera_views'](ui)
        canvas.image_id=1;canvas.status_id=2
        ui.feeds.snapshot.return_value=(Image.new('RGB',(100,80),'blue'),'Live')
        with patch('PIL.ImageTk.PhotoImage',side_effect=lambda image,**kwargs:image.copy()):
            ns['update_camera_views'](ui)
            self.assertEqual(canvas.preview.getpixel((0,0)),(255,0,0))
            self.assertIn('OUTLINES',canvas.itemconfig.call_args.kwargs['text'])
            ui.outline_views['X VIEW']=False
            ns['update_camera_views'](ui)
            self.assertEqual(canvas.preview.getpixel((0,0)),(0,0,255))

    def test_stale_or_sample_geometry_is_never_used_for_live_outlines(self):
        ui,_=self.ui();ui.outline_views['X VIEW']=True
        live=Image.new('RGB',(100,80),'blue')
        for source,stamp in [('live',90),('sample',100),('live',102)]:
            ui.measurements['X VIEW'].update(valid=True,source=source,source_stamp=stamp)
            image,_,status=ui.preview_with_outlines('X VIEW',live,100.9)
            self.assertIs(image,live)
            self.assertIn('unavailable',status)
        ui.overlay.assert_not_called()

if __name__=='__main__':unittest.main()
