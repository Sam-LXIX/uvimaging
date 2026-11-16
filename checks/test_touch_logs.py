"""Verify touch navigation pauses live-follow and scrolls the event table."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

tree=ast.parse((Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text())
ui=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
ns={}
for name in ('scroll_logs','start_log_drag','drag_logs'):
    node=next(n for n in ui.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<touch>','exec'),ns)

class TouchLogTests(unittest.TestCase):
    def test_page_scroll_pauses_follow(self):
        obj=SimpleNamespace(logs_follow=Mock(),logs_tree=Mock())
        self.assertEqual(ns['scroll_logs'](obj,'scroll',1,'pages'),'break')
        obj.logs_follow.set.assert_called_once_with(False)
        obj.logs_tree.yview.assert_called_once_with('scroll',1,'pages')

    def test_drag_scrolls_both_directions(self):
        obj=SimpleNamespace(logs_follow=Mock(),logs_tree=Mock())
        obj.scroll_logs=lambda *args:ns['scroll_logs'](obj,*args)
        ns['start_log_drag'](obj,SimpleNamespace(y=100))
        ns['drag_logs'](obj,SimpleNamespace(y=50))
        obj.logs_tree.yview.assert_called_with('scroll',2,'units')
        ns['drag_logs'](obj,SimpleNamespace(y=100))
        obj.logs_tree.yview.assert_called_with('scroll',-2,'units')
