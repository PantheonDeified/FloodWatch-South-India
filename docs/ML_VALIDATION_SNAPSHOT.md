# FloodWatch ML Validation Snapshot

**Purpose:** submission-time evidence of what has actually been executed. This is a research prototype, not an operational flood-warning service.

## On-demand API inference path

The submission branch adds `GET /api/v1/models/regional-discharge/forecast`. It calls the repository's saved-weight predictor only if the configured ML Python executable, normalized observation file, weights, scalers, evaluation report and predictor script are present. The default ML executable is `~/.local/share/floodwatch-regional-ml/venv/bin/python`. Run `setup`, `preflight`, and `train` on the VM to create those files. If they are absent, the endpoint returns HTTP 503 and `/api/v1/models/status` lists the missing assets.

This makes model inference runnable by request; it does not upgrade the model's scientific status. The regional model still predicts discharge only and uses historical inputs without future rainfall forcing. The current frontend consumes a recent scheduled or API forecast in its experimental map index only through a HydroBASINS same-basin/upstream-chain gate; the contribution is capped at 25% and is not a warning or calibrated flood probability. An actual IBM Z execution claim requires a saved successful VM log and forecast response.


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

The single-station training run [#39115932750](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39115932750) successfully completed the separate saved-weight inference smoke test. It loads the just-trained weights, requires a contiguous 90-day history for the configured station, writes a seven-day CSV forecast plus freshness metadata, and includes those files in the artifact. **The smoke test passing proves the inference code and artifact are usable; it does not prove the forecast is current or safe for warnings.** Check freshness metadata before interpreting forecast values.

The compact model artifact is configured for 90-day retention and excludes the multi-gigabyte normalized source CSV so the downloadable result stays manageable.

## Automated code checks

- [Water-pipeline validation run](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114856351): passed; 35 existing unit tests passed, syntax checks passed, water snapshot validation passed, audit report generation passed.
- [Regional LSTM smoke-test run](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114894196): passed; PyTorch model forward pass, output shape/finite-value check, hand-calculated MAE/RMSE/NSE check, perfect-prediction check, and constant-series NSE handling all passed.
- [Accelerated regional training run #39122959850](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39122959850): passed model training and artifact upload. The report lists 247 source station IDs, 236 stations with usable windows, 8,773 train / 8,423 validation / 13,145 sampled test windows, and a 90-day input with seven-day discharge horizon.

## Verified regional multi-station training result

Source: [regional training run #39122959850](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39122959850), artifact [floodwatch-regional-lstm](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39122959850/artifacts/12134329045). Training lasted 47.27 seconds once historical data had been downloaded and normalized.

| Pooled chronological test metric | Regional LSTM | Persistence baseline |
|---|---:|---:|
| MAE (m³/s) | 93.46 | 106.03 |
| RMSE (m³/s) | 1,121.33 | 2,079.66 |
| NSE | 0.343 | −1.261 |
| Target points | 92,015 | 92,015 |

The pooled RMSE is 46.1% lower than persistence, but station-level skill is uneven: 107 of 223 test stations beat persistence on RMSE; 63 of 119 high-flow station subsets with comparable baselines beat persistence on high-flow RMSE. The report's high-flow subset definition is station-specific 90th-percentile discharge from that station's training period, not an official danger threshold. Some station-level high-flow NSE values are negative.

The 90-day-history, seven-day-output regional LSTM uses historical discharge, an observation mask, day-of-year encoding and station coordinates. The model itself does not use rainfall forcing, verified river-network connectivity or static basin attributes. A separate frontend gate now checks the station's and selected point's HydroBASINS IDs and `NEXT_DOWN` chain before using the discharge percentile; this is not a hydrological model of the channel. It predicts discharge, not flood probability, river level, water depth or inundation. It is a research artifact and must not drive public warnings.

## What the regional model does and does not do

The experimental regional model pools usable time windows from stations in South India and predicts a seven-day discharge sequence. It uses historical discharge, observation masks, day-of-year encoding, and station coordinates. It does **not** ingest rainfall forecasts, weather-model products, river-network connectivity, catchment attributes, or predict flood depth/inundation. A separate single-station research path now accepts forecast rainfall at inference; its training backtest uses later-observed historical reanalysis rain as perfect future forcing and is not an operational model. The frontend's basin-connectivity gate is a spatial association for the regional model output, not a model input. FloodWatch is not equivalent to Google Flood Hub.

## Submission-safe wording

> FloodWatch includes an experimental LSTM for daily river-discharge forecasting. On one Karnataka station's chronological holdout, it reduced RMSE by 18.1% relative to a persistence baseline, while high-flow evaluation remained weak (negative NSE). The pipeline and model smoke tests pass. The accelerated regional multi-station experiment now has a completed report: pooled RMSE is 46.1% lower than persistence, but only 107 of 223 tested stations beat persistence on RMSE and high-flow performance remains mixed. It is not validated for public flood warnings. The model is a research prototype and is not validated for public flood warnings.

Recent station discharge ranks can affect experimental map colours through the basin-connectivity gate; the index remains uncalibrated and is not an official warning. Event-level evaluation can be run with archived map scores and source-reviewed labels using `data_pipeline/scripts/evaluate_map_score_events.py`. No reviewed label archive is bundled, so no event hit rate, false-alarm rate or calibrated probability is reported here.

Do not describe the model as operationally validated, claim city/district-wide flood prediction from this station, or present unverified RMSE figures as regional results.
