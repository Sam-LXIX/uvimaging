"""Host checks for duration presets, migration, and firmware range boundaries."""
import ast
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'LOTUS_UI_Cladding.py').read_text()
C=(ROOT/'firmware/LOTUS_ESP32S3_8MB/main/main.c').read_text()

class UVDurationTests(unittest.TestCase):
    def test_presets_fit_controller(self):
        tree=ast.parse(SOURCE)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='setting_choices')
        presets=ast.literal_eval(method.body[0].value)['Cure duration']
        limit=int(re.search(r'#define UV_MAX_SECONDS (\d+)',C)[1])
        values=[int(p.split()[0]) for p in presets]
        self.assertIn(480,values)
        self.assertEqual(values,sorted(set(values)))
        self.assertTrue(all(1<=n<=limit for n in values))
        self.assertEqual(limit,900)

    def test_upgrade_once_then_preserve_choice(self):
        start=SOURCE.index('        # One-time migration requested for the eight-minute')
        end=SOURCE.index('        # One-time migration for camera',start)
        migration=textwrap.dedent(SOURCE[start:end])
        ui=SimpleNamespace(preferences={'Cure duration':'300 s'})
        exec(migration,{'self':ui,'saved':{'_Cure profile':'300s-v1'}})
        self.assertEqual(ui.preferences['Cure duration'],'480 s')
        ui.preferences['Cure duration']='120 s'
        exec(migration,{'self':ui,'saved':{'_Cure profile':'480s-v2'}})
        self.assertEqual(ui.preferences['Cure duration'],'120 s')

    @unittest.skipUnless(shutil.which('gcc'),'gcc required for host C check')
    def test_actual_firmware_range_function(self):
        function=re.search(r'static bool uv_cure_parameters_valid\([^}]+}',C)[0]
        maximum=re.search(r'#define UV_MAX_SECONDS \d+',C)[0]
        harness='#include <stdbool.h>\n#include <assert.h>\n'+maximum+'\n'+function+'''
int main(void) {
    assert(uv_cure_parameters_valid(480,50));
    assert(uv_cure_parameters_valid(900,100));
    assert(uv_cure_parameters_valid(1,1));
    assert(!uv_cure_parameters_valid(901,50));
    assert(!uv_cure_parameters_valid(0,50));
    assert(!uv_cure_parameters_valid(-1,50));
    assert(!uv_cure_parameters_valid(480,0));
    assert(!uv_cure_parameters_valid(480,101));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'uv.c';out=Path(directory)/'uv'
            src.write_text(harness)
            subprocess.run(['gcc','-Wall','-Wextra','-Werror',str(src),'-o',str(out)],check=True,capture_output=True)
            subprocess.run([str(out)],check=True)
