"""Touch power entry editing without starting cameras or hardware."""
import ast
from pathlib import Path
import unittest

source=(Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text()
cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='power_keypad_edit')
method.decorator_list=[]
ns={}
exec(compile(ast.Module(body=[method],type_ignores=[]),'<keypad>','exec'),ns)
edit=ns['power_keypad_edit']

class PowerKeypadTests(unittest.TestCase):
    def test_fractional_milliwatts(self):
        value=''
        for key in '.025':value=edit(value,key)
        self.assertEqual(value,'0.025')
        self.assertEqual(edit(value,'.'),value)

    def test_existing_value_replacement_and_corrections(self):
        self.assertEqual(edit('400','1',True),'1')
        self.assertEqual(edit('400','.',True),'0.')
        self.assertEqual(edit('400','Backspace',True),'40')
        self.assertEqual(edit('400','Clear'),'')
        self.assertEqual(edit('','Backspace'),'')

    def test_invalid_buttons_do_not_change_value(self):
        for key in ('-','e','12','Done',''):
            self.assertEqual(edit('1.2',key),'1.2')

if __name__=='__main__':unittest.main()
