from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_streamflow_model.py"


class ReviewStreamflowModelTests(unittest.TestCase):
    def test_candidate_that_beats_persistence_is_only_marked_for_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "training.report.json"
            model = root / "model.pt"
            scalers = root / "scalers.npz"
            model.write_bytes(b"fixture")
            scalers.write_bytes(b"fixture")
            report.write_text(json.dumps({
                "station_id": "GAUGE-1",
                "test_windows": 25,
                "beats_persistence_baseline_on_rmse": True,
                "rmse_skill_vs_persistence": 0.12,
                "test_metrics": {"rmse_m3s": 5.0, "mae_m3s": 3.0},
                "persistence_baseline_test_metrics": {"rmse_m3s": 5.7},
                "chronological_split_dates": {"test_starts": "2024-01-01"},
            }), encoding="utf-8")
            run = subprocess.run([
                sys.executable, str(SCRIPT), "--report", str(report),
                "--model", str(model), "--scalers", str(scalers),
            ], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            result = json.loads(run.stdout)
            self.assertEqual(result["status"], "eligible_for_human_review")
            self.assertFalse(result["automatically_deployed"])

    def test_candidate_that_does_not_beat_persistence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "training.report.json"
            model = root / "model.pt"
            scalers = root / "scalers.npz"
            model.write_bytes(b"fixture")
            scalers.write_bytes(b"fixture")
            report.write_text(json.dumps({
                "station_id": "GAUGE-1",
                "test_windows": 25,
                "beats_persistence_baseline_on_rmse": False,
                "rmse_skill_vs_persistence": -0.2,
                "test_metrics": {"rmse_m3s": 6.0, "mae_m3s": 4.0},
                "persistence_baseline_test_metrics": {"rmse_m3s": 5.0},
                "chronological_split_dates": {"test_starts": "2024-01-01"},
            }), encoding="utf-8")
            run = subprocess.run([
                sys.executable, str(SCRIPT), "--report", str(report),
                "--model", str(model), "--scalers", str(scalers),
            ], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            result = json.loads(run.stdout)
            self.assertEqual(result["status"], "not_eligible_for_review")
            self.assertIn("beats_persistence_baseline", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
