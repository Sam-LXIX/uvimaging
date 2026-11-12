"""Headless tests: no cameras, serial ports, or GPIO are opened."""
import ast
import math
from collections import deque
from pathlib import Path
import unittest

source = (Path(__file__).resolve().parents[1] / 'LOTUS_UI_Cladding.py').read_text()
tree = ast.parse(source)
namespace = {'math': math, 'deque': deque}
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BatteryEstimate')
exec(compile(ast.Module(body=[node], type_ignores=[]), '<battery>', 'exec'), namespace)
BatteryEstimate = namespace['BatteryEstimate']

def state(voltage=11.4, stamp=100, **extra):
    return dict(connected=True, inaok=1, voltage=voltage, _status_monotonic=stamp, **extra)

class BatteryTests(unittest.TestCase):
    def test_range_and_monotonicity(self):
        results = [BatteryEstimate().update(state(v / 100), 'Battery alone', 100)[0]
                   for v in range(800, 1281)]
        self.assertEqual(results, sorted(results))
        self.assertEqual((results[0], results[-1]), (0, 100))

    def test_stale_offline_bad_sensor_and_invalid(self):
        for changes in ({'connected': False}, {'inaok': 0}, {'voltage': float('nan')},
                        {'voltage': float('inf')}, {'voltage': None}, {'voltage': 5},
                        {'voltage': 14}, {'_status_monotonic': 97},
                        {'_status_monotonic': 101}, {'_status_monotonic': None}):
            sample = state(); sample.update(changes)
            self.assertIsNone(BatteryEstimate().update(sample, 'Battery alone', 100)[0])

    def test_charging_hides_estimate_and_clears_history(self):
        gauge = BatteryEstimate()
        gauge.update(state(), 'Battery alone', 100)
        self.assertIsNone(gauge.update(state(), 'External / charging', 100)[0])
        self.assertFalse(gauge.samples)

    def test_duplicate_samples_not_counted_and_spike_filtered(self):
        gauge = BatteryEstimate()
        for t in (100, 101, 102):
            gauge.update(state(stamp=t), 'Battery alone', t)
        for _ in range(20):
            gauge.update(state(9, 103), 'Battery alone', 103)
        self.assertEqual(len(gauge.samples), 4)
        self.assertEqual(gauge.update(state(9, 103), 'Battery alone', 103)[0], 50)

    def test_reconnect_starts_new_window(self):
        gauge = BatteryEstimate()
        gauge.update(state(12.6), 'Battery alone', 100)
        self.assertEqual(gauge.update(state(10.5, 110), 'Battery alone', 110), (10, 'Low'))

    def test_snapshot_voltage_is_rough_low_estimate(self):
        self.assertEqual(BatteryEstimate().update(state(10.632), 'Battery alone', 100), (15, 'Low'))

if __name__ == '__main__':
    unittest.main()
