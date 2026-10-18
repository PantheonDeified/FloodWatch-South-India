from __future__ import annotations
import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"adapt_cwc_discharge_observations.py"

class CwcAdapterTests(unittest.TestCase):
    def test_converts_schema_and_preserves_provenance_without_claiming_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"in.csv"; out=root/"out.csv"; report=root/"report.json"
            fields=["station_id","station_name","state","district","river","basin","latitude","longitude","observed_at","discharge_m3_s","source_url","source_file","source_timezone","quality_flag"]
            row={"station_id":"s1","station_name":"Gauge A","state":"Kerala","district":"D1","river":"River A","basin":"B1","latitude":"10","longitude":"76","observed_at":"2020-01-01T08:00","discharge_m3_s":"12.5","source_url":"https://example.gov/data","source_file":"source.csv","source_timezone":"unspecified","quality_flag":"unreviewed"}
            with src.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow(row)
                w.writerow({**row,"station_id":"s2","discharge_m3_s":"-1"})
            run=subprocess.run([sys.executable,str(SCRIPT),"--input",str(src),"--output",str(out),"--report",str(report)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            with out.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1); self.assertEqual(rows[0]["kind"],"river_discharge")
            self.assertEqual(rows[0]["unit"],"m3/s"); self.assertEqual(rows[0]["source_url"],row["source_url"])
            result=json.loads(report.read_text()); self.assertEqual(result["rows_skipped"],1)
            self.assertEqual(result["status"],"schema_conversion_only_not_data_validation")
    def test_rejects_missing_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"bad.csv"; src.write_text("station_id,state\na,Kerala\n")
            run=subprocess.run([sys.executable,str(SCRIPT),"--input",str(src),"--output",str(root/"out.csv")],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
if __name__=="__main__": unittest.main()
