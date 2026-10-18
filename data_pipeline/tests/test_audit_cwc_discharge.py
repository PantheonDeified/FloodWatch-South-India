from __future__ import annotations
import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_cwc_discharge.py"

class DischargeAuditTests(unittest.TestCase):
    def test_reports_gaps_duplicates_and_extreme_values_without_deleting_data(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"normalized.csv"; out=root/"audit.json"
            fields=["station_id","station_name","state","river","basin","observed_at","discharge_m3_s","source_url"]
            base={"station_id":"s1","station_name":"Gauge A","state":"Kerala","river":"River A","basin":"Basin A","source_url":"https://example.gov"}
            with src.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
                w.writerow({**base,"observed_at":"2020-01-01T08:00","discharge_m3_s":"10"})
                w.writerow({**base,"observed_at":"2020-01-01T10:00","discharge_m3_s":"12"})
                w.writerow({**base,"observed_at":"2020-01-04T08:00","discharge_m3_s":"120001"})
            run=subprocess.run([sys.executable,str(SCRIPT),"--input",str(src),"--output",str(out)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            result=json.loads(out.read_text(encoding="utf-8")); station=result["station_reports"][0]
            self.assertEqual(station["row_count"],3)
            self.assertEqual(station["duplicate_rows_on_same_date"],1)
            self.assertEqual(station["missing_calendar_days"],2)
            self.assertIn("same_date_duplicates",station["review_flags"])
            self.assertIn("large_values_require_domain_review",station["review_flags"])

if __name__=="__main__": unittest.main()
