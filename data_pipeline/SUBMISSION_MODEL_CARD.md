# FloodWatch ML / neural-network status card

Last repository review: 2026-10-18.

## Accurate status for a demo

FloodWatch has a completed experimental single-station LSTM pilot and a completed five-state regional discharge LSTM training/inference run. The current validation-selected LSTM/persistence blend improves pooled test RMSE over persistence, although raw LSTM predictions alone are weaker. The model is still a discharge-only research prototype: it has no future rainfall forcing, no validated station-to-river routing, and is not deployed to the public risk map or validated for public flood warnings.

| Capability | Status | Evidence |
|---|---|---|
| Regional neural-network weights | Trained artifact exists | [Five-state training run #39126986154](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39126986154), artifact [floodwatch-regional-lstm](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39126986154/artifacts/12136079681). |
| Regional model evaluation | Completed on chronological holdout | 89,824 pooled test targets; raw LSTM RMSE 830.45 m³/s, persistence RMSE 700.88 m³/s, selected blend RMSE 649.63 m³/s. The blend weight (alpha=0.25) was chosen solely on chronological validation data; held-out RMSE is 7.3% lower than persistence. |
| Per-station robustness | Mixed; not a pass for deployment | The selected blend beat persistence on RMSE at 135/218 evaluated stations and at 78/116 comparable high-flow station subsets. Raw LSTM alone beat persistence at fewer stations. Results vary substantially and are not deployment-validated. |
| Reproducible inference | Predictor script is included in main; workflow runs saved-weight inference and uploads the forecast artifact | data_pipeline/scripts/predict_regional_lstm.py loads the saved weights/scalers, applies the validation-selected blend weight, and emits a seven-day experimental discharge sequence. Latest smoke test passed; one-day source timestamp age is a freshness heuristic, not independent proof of real-time sensor transmission. |
| Single-station neural-network pilot | Previously trained | Yadgir station holdout RMSE was 1,043.61 m³/s vs persistence 1,274.75 m³/s; high-flow NSE was −0.013, so extreme-flow reliability remains weak. |
| ML event classifier | Prototype code exists | data_pipeline/scripts/train_event_ml.py implements a scikit-learn classifier with chronological evaluation. It needs reviewed event labels before flood-event claims. |
| Calibrated flood probability / inundation map | Not available | Neither discharge LSTM estimates flood probability, water depth, inundation extent, evacuation routes nor household impact. |

## Regional training configuration and metrics

The five-state run used a 90-day input history, seven-day forecast horizon, a 48-unit single-layer LSTM, batch size 512, six requested epochs, patience two and two CPU threads. Cached model fitting took 21.53 seconds; first-time archive retrieval and normalization take longer. A simple LSTM/persistence blend weight was selected using the chronological validation split only, then evaluated once on the held-out test split.

| Pooled chronological test metric | Validation-selected blend | Raw LSTM | Persistence |
|---|---:|---:|---:|
| MAE (m³/s) | 75.70 | 90.03 | 79.82 |
| RMSE (m³/s) | 649.63 | 830.45 | 700.88 |
| NSE | 0.652 | 0.432 | 0.595 |
| Test targets | 89,824 | 89,824 | 89,824 |

The latest five-state report used 241 source station IDs and produced usable forecast windows for 231. Source records extend through 2026-10-17. The chronological holdout begins 2017-07-11 and contains 89,824 sampled targets; windows are time-sampled per station rather than exhaustive. The raw LSTM alone is weaker than persistence, but the validation-selected blend (alpha=0.25; 25% LSTM plus 75% persistence) achieves 7.3% lower pooled test RMSE. The selected blend beats persistence on RMSE at 135/218 evaluated stations and 78/116 comparable high-flow station subsets. Timestamp age is a freshness heuristic only; station coordinate identity, provider update cadence, extreme-flow skill and river-network links still need independent review. Repeated comparisons to this same held-out window are not a substitute for a future independent test period.

Interpretation: the model is a meaningful training milestone, not an operational flood-prediction model. A physical discharge value, a station-relative high-flow threshold and an official flood-warning level are distinct concepts.

## Current five-state retraining

Latest completed run: https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39126986154 (artifact ID 12136079681). Training scope is exactly Andhra Pradesh, Karnataka, Kerala, Tamil Nadu and Telangana; downloaded/normalized data are cached by day and pipeline version, with the workflow requesting data through the current UTC year. Training, validation-selected blending, saved-weight inference and artifact upload passed. The inference example used records through 2026-10-17, one day before the workflow; this is a timestamp-freshness check, not independent proof of live sensor transmission.

## What the network uses

The model's six daily sequence features are scaled log-transformed historical discharge, an observation mask, day-of-year sine/cosine, and station latitude/longitude. It predicts a seven-day discharge sequence. It does not consume rainfall forecast forcing, upstream/downstream river-network connectivity, validated catchment attributes or a hydraulic inundation model. It does not infer a dam's structural strength.

The separate frontend risk score is not the LSTM: it currently uses Open-Meteo gridded forecast inputs, GloFAS discharge-model context and sufficiently fresh gauge history, plus manually entered source-linked human-made incidents when evidence meets documented guardrails. NASA IMERG imagery is visual context, not silently mixed into the numeric score. Risk contour colours are an experimental project-defined score, not a calibrated probability.

## Guardrails before deployment

1. Keep train/validation/test time order and fit scaling values only on training-period records.
2. Retain source URLs, station identity, units, valid time and quality flags; a data-archive time range alone is not enough.
3. Report pooled, station-specific, lead-specific and high-flow metrics against a persistence baseline. Here the pooled result improves while many individual stations and a substantial fraction of high-flow subsets do not.
4. Independently validate station coordinates, basin/routing relationships, high-flow events, data freshness and uncertainty.
5. Keep model output disconnected from the public risk map until a reviewed inference service, monitoring, uncertainty and clear model status are in place.
6. Never treat missing input as zero, green/safe, or evidence of no flood. Official IMD, CWC and state disaster-management warnings remain authoritative.

## Research references

- CWC/NWIC river telemetry: https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc
- Open-Meteo Flood API / GloFAS context: https://open-meteo.com/en/docs/flood-api
- Google Research flood-forecasting implementation: https://github.com/google-research/flood-forecasting
- Caravan hydrological data reference: https://github.com/kratzert/Caravan
- HydroBASINS catchment polygons: https://www.hydrosheds.org/products/hydrobasins

Do not claim parity with Google Flood Hub. Its public open-source research code is not the entire production service. FloodWatch remains a research prototype and is not an official warning system.
