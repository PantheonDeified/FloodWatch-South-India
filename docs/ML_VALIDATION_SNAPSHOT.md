# FloodWatch ML Validation Snapshot

**Purpose:** submission-time evidence of what has actually been executed. This is a research prototype, not an operational flood-warning service.

## Verified single-station LSTM run

Source: [GitHub Actions run #39114067094](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114067094), artifact `floodwatch-discharge-lstm-4`.

- Station: Yadgir, Karnataka (station key includes coordinates 16.7375, 77.1253).
- Target: daily maximum observed river discharge (m³/s).
- Input: previous observed discharge only; no rainfall or forecast weather inputs.
- Period: 1965-06-01 to 2025-12-31; 21,935 observed days and 194 missing calendar days.
- Chronological windows: 14,725 training, 2,082 validation, 2,995 test windows.
- Evaluation is a time-ordered holdout, with test data beginning 2016-11-29.

| Test metric | LSTM | Persistence baseline |
|---|---:|---:|
| MAE (m³/s) | 237.77 | 249.03 |
| RMSE (m³/s) | 1,043.61 | 1,274.75 |
| NSE | 0.357 | 0.041 |

Overall test RMSE skill versus persistence is approximately **18.1%**. This is evidence that the trained model beat persistence on this station's overall holdout set; it is not evidence of reliable flood warnings.

### Critical limitation: high-flow performance

For the report's high-flow subset (threshold 797.7 m³/s), the LSTM has MAE 1,352.76 m³/s, RMSE 2,957.05 m³/s, and NSE -0.013. Negative NSE means it performed worse than predicting the subset mean under that metric. Extreme-flow behaviour is therefore not good enough to claim flood-event reliability.

## Trained-weight inference smoke test

I also loaded the actual saved `.pt` weights and matching `.scalers.npz` from the completed single-station training artifact, selected the same station's latest 90 consecutive observed days, and ran a CPU forward forecast. The model loaded successfully and returned seven finite non-negative discharge estimates. The archive's last observed day was **2025-12-31**, so the generated forecast dates were **2026-01-01 through 2026-01-07**; this is a functional inference test on stale historical input, **not a current forecast**.

The single-station GitHub Actions workflow now runs this inference smoke test after training and includes its CSV and freshness metadata in the model artifact. The compact artifact is configured for 90-day retention and excludes the multi-gigabyte normalized source CSV.

## Automated code checks

- [Water-pipeline validation run](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114856351): passed; 35 existing unit tests passed, syntax checks passed, water snapshot validation passed, audit report generation passed.
- [Regional LSTM smoke-test run](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114894196): passed; PyTorch model forward pass, output shape/finite-value check, hand-calculated MAE/RMSE/NSE check, perfect-prediction check, and constant-series NSE handling all passed.
- [Regional training run](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114366885): a separate regional multi-station model training/evaluation attempt. Its result must be read from its completed run and artifact; do not substitute single-station metrics for it.

## What the regional model does and does not do

The experimental regional model pools usable time windows from stations in South India and predicts a seven-day discharge sequence. It uses historical discharge, observation masks, day-of-year encoding, and station coordinates. It does **not** currently ingest rainfall forecasts, weather-model products, river-network connectivity, catchment attributes, or predict flood depth/inundation. It is not equivalent to Google Flood Hub.

## Submission-safe wording

> FloodWatch includes an experimental LSTM for daily river-discharge forecasting. On one Karnataka station's chronological holdout, it reduced RMSE by 18.1% relative to a persistence baseline, while high-flow evaluation remained weak (negative NSE). The pipeline and model smoke tests pass. Regional multi-station performance is reported separately only after that run completes and its evaluation artifact is inspected. The model is a research prototype and is not validated for public flood warnings.

Do not describe the model as operationally validated, claim city/district-wide flood prediction from this station, or present unverified RMSE figures as regional results.
