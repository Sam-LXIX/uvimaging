"""Exercise startup mapping and menu visibility without cameras or controller."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

source=(Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text()
cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
names={'set_fullscreen','toggle_fullscreen','startup_window_mapped','apply_startup_fullscreen','apply_sidebar_visibility'}
cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
cls.bases=[]
ns={}
exec(compile(ast.Module(body=[cls],type_ignores=[]),'<layout>','exec'),ns)

class Widget:
    def __init__(self):self.calls=[]
    def winfo_exists(self):return True
    def pack(self,**kwargs):self.calls.append(('pack',kwargs))
    def pack_forget(self):self.calls.append(('hide',{}))
    def pack_configure(self,**kwargs):self.calls.append(('configure',kwargs))
    def config(self,**kwargs):self.calls.append(('config',kwargs))

class StartupLayoutTests(unittest.TestCase):
    def ui(self):
        ui=ns['LotusUI']()
        ui.startup_fullscreen_pending=True;ui.startup_fullscreen_scheduled=False;ui.closing=False
        ui.events=[];ui.scheduled=[];ui.fullscreen=False
        def attributes(key,*value):
            if value:ui.fullscreen=value[0];ui.events.append(value[0])
            return ui.fullscreen
        ui.attributes=attributes
        ui.after_idle=lambda callback:ui.scheduled.append(callback)
        ui.after=lambda delay,callback:ui.scheduled.append(callback)
        ui.menu_button=Widget();ui.brand_frame=Widget();ui.sidebar_visible=True
        return ui

    def test_map_requests_fullscreen_after_window_appears(self):
        ui=self.ui()
        ui.startup_window_mapped(SimpleNamespace(widget=object()))
        self.assertFalse(ui.scheduled)
        ui.startup_window_mapped(SimpleNamespace(widget=ui))
        for callback in ui.scheduled:callback()
        self.assertTrue(ui.fullscreen)
        self.assertEqual(ui.events,[True,True,True])
        self.assertFalse(ui.startup_fullscreen_pending)

    def test_operator_exit_cancels_delayed_requests(self):
        ui=self.ui();ui.startup_window_mapped(SimpleNamespace(widget=ui))
        ui.scheduled[0]()
        ui.set_fullscreen(False)
        for callback in ui.scheduled[1:]:callback()
        self.assertFalse(ui.fullscreen)
        ui.toggle_fullscreen();self.assertTrue(ui.fullscreen)

    def test_windowed_mode_does_not_schedule_fullscreen(self):
        ui=self.ui();ui.startup_fullscreen_pending=False
        ui.startup_window_mapped(SimpleNamespace(widget=ui))
        self.assertFalse(ui.scheduled)

    def test_menu_hidden_without_sidebar_and_restored_on_other_pages(self):
        ui=self.ui();ui.sidebar_frame=None;ui.page_main=None
        ui.apply_sidebar_visibility()
        self.assertEqual(ui.menu_button.calls[-1][0],'hide')
        ui.sidebar_frame=Widget();ui.page_main=Widget()
        ui.apply_sidebar_visibility()
        self.assertIn(('config',{'text':'Hide menu'}),ui.menu_button.calls)
        ui.sidebar_visible=False;ui.apply_sidebar_visibility()
        self.assertEqual(ui.sidebar_frame.calls[-1][0],'hide')
        self.assertEqual(ui.menu_button.calls[-1],('config',{'text':'Menu'}))

if __name__=='__main__':unittest.main()
