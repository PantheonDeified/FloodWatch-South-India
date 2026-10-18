"""End-to-end smoke test for regional LSTM input preprocessing and inference."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
import torch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from train_regional_lstm import RegionalLSTM


class RegionalInferenceTests(unittest.TestCase):
    def test_inference_emits_seven_nonnegative_predictions(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            today = dt.date.today()
            dates = [today - dt.timedelta(days=i) for i in range(120, 0, -1)]
            rows = []
            for i, day in enumerate(dates):
                if i in {25, 61, 87}:  # Exercise the missing-day mask safely.
                    continue
                rows.append({
                    "station_id": "test-gauge-01",
                    "state": "Karnataka",
                    "latitude": 14.0,
                    "longitude": 77.0,
                    "observed_at": day.isoformat(),
                    "discharge_m3_s": 20.0 + (i % 17) * 2.5,
                })
            observations = root / "observations.csv"
            pd.DataFrame(rows).to_csv(observations, index=False)
            model_path = root / "model.pt"
            scaler_path = root / "scalers.json"
            report_path = root / "report.json"
            output_path = root / "forecast.json"

            model = RegionalLSTM(horizon=7)
            torch.save(model.state_dict(), model_path)
            scaler_path.write_text(json.dumps({
                "discharge_log1p_mean": 3.5,
                "discharge_log1p_std": 1.1,
                "latitude_divisor": 90.0,
                "longitude_divisor": 180.0,
            }), encoding="utf-8")
            report_path.write_text(json.dumps({
                "model_type": "test regional LSTM",
                "lookback_days": 90,
                "lead_days": 7,
            }), encoding="utf-8")

            predictor = SCRIPTS / "predict_regional_lstm.py"
            result = subprocess.run([
                sys.executable, str(predictor),
                "--observations", str(observations),
                "--model-file", str(model_path),
                "--scalers-file", str(scaler_path),
                "--report-file", str(report_path),
                "--output-file", str(output_path),
            ], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, msg=result.stdout + "\n" + result.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["station_id"], "test-gauge-01")
            self.assertEqual(len(payload["forecast"]), 7)
            predictions = [p["predicted_discharge_m3_s"] for p in payload["forecast"]]
            self.assertTrue(all(np.isfinite(v) and v >= 0 for v in predictions))
            last = payload["last_observed_discharge_m3_s"]
            self.assertTrue(all(p["persistence_baseline_discharge_m3_s"] == last for p in payload["forecast"]))
            self.assertEqual(payload["status"], "experimental_research_only")


if __name__ == "__main__":
    unittest.main()
