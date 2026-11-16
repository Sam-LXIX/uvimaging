"""Classify real controller messages without opening hardware or a Tk window."""
import ast
from pathlib import Path
import unittest

source = (Path(__file__).resolve().parents[1] / 'LOTUS_UI_Cladding.py').read_text()
ui = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'LotusUI')
namespace = {}
for name in ('log_categories', 'log_severity'):
    method = next(n for n in ui.body if isinstance(n, ast.FunctionDef) and n.name == name)
    method.decorator_list = []
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<logs>', 'exec'), namespace)

class LogViewerTests(unittest.TestCase):
    def test_subsystems(self):
        for message, category in [('TX UV_CURE 300 100', 'UV Cure'),
                ('RX EVENT UV_DONE', 'UV Cure'), ('TX MOVE X 500 1000', 'Motors / Alignment'),
                ('AUTO XYZ START', 'Motors / Alignment'), ('TX LIGHT 12.5', 'Cameras'),
                ('CAMERA Y VIEW: Live', 'Cameras'), ('RX OK FAN percent=50', 'Fan'),
                ('RX STATUS voltage=12.1', 'Sensors / Power'),
                ('ESP32 disconnected', 'Connection / Errors')]:
            with self.subTest(message=message):
                self.assertIn(category, namespace['log_categories'](message))

    def test_severity(self):
        for message, level in [('RX ERR UV not_armed', 'ERROR'), ('FAN ERROR timeout', 'ERROR'),
                ('CAMERA Y VIEW: Frame error', 'ERROR'), ('EMERGENCY STOP', 'ERROR'),
                ('ESP32 disconnected', 'WARNING'), ('Camera not detected by Pi', 'WARNING'),
                ('No recent frames — retry cameras', 'WARNING'), ('Not confirmed: no reply', 'WARNING'),
                ('TX UV_STOP', 'INFO'), ('RX OK FAN percent=50', 'INFO'),
                ('CAMERA Y VIEW: Live', 'INFO')]:
            with self.subTest(message=message):
                self.assertEqual(namespace['log_severity'](message), level)
