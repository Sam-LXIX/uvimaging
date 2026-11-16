"""Saved log exports preserve every event and expose user-readable measurements."""
import ast
import csv
import io
import json
import tempfile
import unittest
from collections import deque
from datetime import datetime
from pathlib import Path

source=(Path(__file__).resolve().parents[1]/'LOTUS_UI_Cladding.py').read_text()
ui=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
names=('log_categories','log_severity','readable_log_message','readable_measurement',
       'read_saved_log_records','saved_log_exports')
ui.body=[n for n in ui.body if isinstance(n,ast.FunctionDef) and n.name in names]
ui.bases=[]
ns=dict(json=json,deque=deque,datetime=datetime,io=io,csv=csv)
exec(compile(ast.Module(body=[ui],type_ignores=[]),'<saved logs>','exec'),ns)

class SavedLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ui=ns['LotusUI']()
        self.ui.data_dir=Path(self.tmp.name)

    def write(self,name,records):
        (self.ui.data_dir/name).write_text('\n'.join(json.dumps(r) for r in records),encoding='utf-8')

    def test_requests_are_not_confirmation(self):
        self.assertEqual(self.ui.readable_log_message('TX STOP'),'Stop requested')
        self.assertEqual(self.ui.readable_log_message('RX OK FAN AUTO'),'Controller confirmed: FAN AUTO')
        self.assertEqual(self.ui.readable_log_message('RX ERR UV not_armed'),'Controller reported an error: UV not_armed')

    def test_complete_chronological_export_and_units(self):
        self.write('hardware.jsonl',[{'time':f'2026-11-16T02:{i:04d}','event':'TX STOP'} for i in range(2005)])
        self.write('verification.jsonl',[{'time':'2026-11-15T01:00:00','input_power_mw':1,
            'output_power_mw':0.9,'loss_db':0.4576,'pf1_mw':1,'method':'calculated_from_manual_optical_power_readings'}])
        txt,table=self.ui.saved_log_exports()
        rows=list(csv.reader(io.StringIO(table)))
        self.assertEqual(len(rows),2007)
        self.assertIn('Input power: 1.000 mW',rows[1][3])
        self.assertIn('Calculated loss: 0.458 dB',rows[1][3])
        self.assertEqual(rows[2][-1],'TX STOP')
        self.assertIn('Entries: 2006',txt)
        self.assertEqual(len(self.ui.read_saved_log_records(limit=2000)),2001)

    def test_damaged_record_and_csv_escaping(self):
        (self.ui.data_dir/'hardware.jsonl').write_text('{bad json}\n'+json.dumps({'event':'=1+2, "raw"'}))
        txt,table=self.ui.saved_log_exports()
        rows=list(csv.reader(io.StringIO(table)))
        self.assertIn('Unreadable saved entry',txt)
        self.assertEqual(rows[2][3],"'=1+2, \"raw\"")
        self.assertEqual(rows[1][2],'WARNING')

    def test_empty_export(self):
        text,table=self.ui.saved_log_exports()
        self.assertIn('No saved events found.',text)
        self.assertEqual(len(list(csv.reader(io.StringIO(table)))),1)

if __name__=='__main__':unittest.main()
