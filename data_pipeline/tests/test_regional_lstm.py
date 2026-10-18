"""Fast smoke tests for the experimental regional LSTM (requires numpy and torch)."""
import importlib.util
import pathlib
import unittest

import numpy as np

try:
    import torch
except ImportError:
    torch = None

if torch is not None:
    SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "train_regional_lstm.py"
    SPEC = importlib.util.spec_from_file_location("train_regional_lstm", SCRIPT)
    MODULE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MODULE)
else:
    MODULE = None


@unittest.skipIf(torch is None, "regional LSTM smoke tests require PyTorch; run test-regional-lstm workflow")
class RegionalLSTMTests(unittest.TestCase):
    def test_forward_shape_and_finite_output(self):
        model = MODULE.RegionalLSTM(horizon=7)
        x = torch.zeros((3, 90, 6), dtype=torch.float32)
        y = model(x)
        self.assertEqual(tuple(y.shape), (3, 7))
        self.assertTrue(torch.isfinite(y).all().item())

    def test_metrics_against_hand_calculation(self):
        actual = np.array([1.0, 2.0, 3.0])
        predicted = np.array([1.0, 2.0, 5.0])
        result = MODULE.metrics(actual, predicted)
        self.assertAlmostEqual(result["mae_m3s"], 2.0 / 3.0)
        self.assertAlmostEqual(result["rmse_m3s"], np.sqrt(4.0 / 3.0))
        self.assertEqual(result["samples"], 3)
        self.assertLess(result["nse"], 1.0)

    def test_perfect_prediction_metrics(self):
        actual = np.array([0.0, 2.0, 5.0])
        result = MODULE.metrics(actual, actual.copy())
        self.assertEqual(result["mae_m3s"], 0.0)
        self.assertEqual(result["rmse_m3s"], 0.0)
        self.assertAlmostEqual(result["nse"], 1.0)

    def test_constant_series_has_undefined_nse(self):
        result = MODULE.metrics(np.array([4.0, 4.0]), np.array([4.0, 5.0]))
        self.assertIsNone(result["nse"])

    def test_regional_training_scope_is_exactly_the_five_target_states(self):
        source = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "train_regional_lstm.py").read_text(encoding="utf-8")
        for state in ("Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"):
            self.assertIn(state, source)
        self.assertNotIn('"Puducherry"', source)
        self.assertNotIn('"Goa"', source)

    def test_inference_keeps_training_feature_scale_and_marks_stale_history(self):
        predictor = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "predict_regional_lstm.py"
        source = predictor.read_text(encoding="utf-8")
        self.assertIn('frame["latitude"] = frame["latitude"].clip(-90, 90) / 90.0', source)
        self.assertIn('frame["longitude"] = frame["longitude"].clip(-180, 180) / 180.0', source)
        self.assertIn('"forecast_is_live": bool(history_age_days <= 3)', source)
        self.assertIn('"history_freshness": history_freshness', source)
        self.assertIn('model.load_state_dict(weights, strict=True)', source)

    def test_training_coordinates_are_scaled_once_and_match_inference(self):
        trainer = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "train_regional_lstm.py"
        source = trainer.read_text(encoding="utf-8")
        self.assertIn('pd.to_numeric(df.latitude, errors="coerce").fillna(0).clip(-90,90)/90', source)
        self.assertIn('pd.to_numeric(df.longitude, errors="coerce").fillna(0).clip(-180,180)/180', source)
        self.assertIn('lat,lon=map(float,meta.loc[sid].tolist())', source)
        self.assertNotIn('lat_raw,lon_raw=map(float,meta.loc[sid].tolist())', source)


if __name__ == "__main__":
    unittest.main()
