"""Settings dialogs must release input capture and reopen after closing."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

source=(Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text()
cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
ns={}
for name in ('close_setting_choices','settings_feedback'):
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[method],type_ignores=[]),'<settings>','exec'),ns)

class SettingsDialogTests(unittest.TestCase):
    def test_close_releases_grab_and_forgets_window(self):
        events=[]
        top=SimpleNamespace(winfo_exists=lambda:True,grab_release=lambda:events.append('release'),
                            destroy=lambda:events.append('destroy'))
        top.grab_current=lambda:top
        ui=SimpleNamespace(settings_choice_window=top)
        ns['close_setting_choices'](ui)
        self.assertEqual(events,['release','destroy'])
        self.assertIsNone(ui.settings_choice_window)
        ns['close_setting_choices'](ui)
        self.assertEqual(events,['release','destroy'])

    def test_old_dialog_does_not_release_another_dialog_grab(self):
        events=[]
        top=SimpleNamespace(winfo_exists=lambda:True,grab_current=lambda:object(),
             grab_release=lambda:events.append('release'),destroy=lambda:events.append('destroy'))
        ns['close_setting_choices'](SimpleNamespace(settings_choice_window=top))
        self.assertEqual(events,['destroy'])

    def test_feedback_ignores_destroyed_page(self):
        label=SimpleNamespace(winfo_exists=lambda:False,config=lambda **kwargs:self.fail('Destroyed label updated'))
        ns['settings_feedback'](SimpleNamespace(settings_feedback_label=label),'Pending')

if __name__=='__main__':unittest.main()
