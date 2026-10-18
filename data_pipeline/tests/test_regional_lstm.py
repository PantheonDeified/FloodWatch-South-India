"""Fast smoke tests for the experimental regional LSTM (requires numpy and torch)."""
import importlib.util
import pathlib
import unittest

import numpy as np
import torch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "train_regional_lstm.py"
SPEC = importlib.util.spec_from_file_location("train_regional_lstm", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


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


if __name__ == "__main__":
    unittest.main()
