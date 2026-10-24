# FloodWatch ML / neural-network status card

Last repository review: 2026-10-24.

## Accurate status for a demo

FloodWatch has a completed experimental single-station LSTM pilot and a completed five-state regional discharge LSTM training/inference run. The current validation-selected LSTM/persistence blend improves pooled test RMSE over persistence, although raw LSTM predictions alone are weaker. The regional model is an executable discharge-only research pipeline; a separate single-station rainfall-forced experiment accepts future rain at inference but is not deployed. The backend supports regional on-demand forecasts when saved weights and inputs are installed. The frontend uses recent station-relative discharge ranks as a limited modifier to its experimental risk-score colours only across a HydroBASINS same-basin or upstream `NEXT_DOWN` connection. No independently labelled event set is bundled, and the basin association is not validated river-channel routing. No calibrated flood probability is produced.

| Capability | Status | Evidence |
|---|---|---|
| Regional neural-network weights | Trained artifact exists | [Five-state training run #39126986154](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39126986154), artifact [floodwatch-regional-lstm](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39126986154/artifacts/12136079681). |
| Regional model evaluation | Completed on chronological holdout | 89,824 pooled test targets; raw LSTM RMSE 830.45 m³/s, persistence RMSE 700.88 m³/s, selected blend RMSE 649.63 m³/s. The blend weight (alpha=0.25) was chosen solely on chronological validation data; held-out RMSE is 7.3% lower than persistence. |
| Per-station robustness | Mixed; not a pass for deployment | The selected blend beat persistence on RMSE at 135/218 evaluated stations and at 78/116 comparable high-flow station subsets. Raw LSTM alone beat persistence at fewer stations. Results vary substantially and are not deployment-validated. |
| Reproducible inference | CI predictor smoke test plus gated on-demand API route | `data_pipeline/scripts/predict_regional_lstm.py` loads saved weights/scalers and emits seven daily discharge predictions. The API supports `all_stations=true` to return eligible station coordinates and station-relative historic discharge ranks. Inference still requires normalized history, weights, scalers, report and the ML virtualenv; missing assets return HTTP 503. The actual VM path must pass setup/preflight/train before it is claimed as running there. |
| Station-aware map-score contribution | Implemented in the frontend | Recent snapshot or API forecasts with usable coordinates and station-relative discharge ranks can affect a map score by at most 25% only when HydroBASINS `NEXT_DOWN` links connect the station sub-basin to the selected point's basin (same basin or up to six downstream links). Unmapped or disconnected points receive no adjustment. This is basin-level screening, not verified channel routing or a probability. |
| Rainfall-forced discharge experiment | Research pipeline added; not deployed | `train_rainfall_forced_lstm.py` and `predict_rainfall_forced_lstm.py` accept historical features and a lead-day rainfall forecast. Backtesting uses reanalysis rainfall observed after the forecast origin as perfect future forcing, so results are an optimistic upper bound. It needs out-of-time evaluation with real weather forecasts before any deployment consideration. |
| Single-station neural-network pilot | Previously trained | Yadgir station holdout RMSE was 1,043.61 m³/s vs persistence 1,274.75 m³/s; high-flow NSE was −0.013, so extreme-flow reliability remains weak. |
| Event-based map-index verification | Evaluation pipeline and browser score export available | `data_pipeline/scripts/evaluate_map_score_events.py` reports chronological raw-index and calibrated metrics from archived scores and source-reviewed labels. The project does not bundle enough reviewed labels to report event accuracy. |
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

The frontend base score uses Open-Meteo gridded rainfall forecasts and GloFAS river-discharge context, plus source-linked human-made incident records that satisfy documented guardrails. When the optional LSTM API is configured, a station-relative forecast-peak discharge rank can adjust cells near eligible stations by up to 25%, fading with distance. NASA IMERG imagery is visual context, not silently mixed into the numeric score. Risk contour colours remain an experimental project-defined score, not a calibrated probability.

## Guardrails before deployment

1. Keep train/validation/test time order and fit scaling values only on training-period records.
2. Retain source URLs, station identity, units, valid time and quality flags; a data-archive time range alone is not enough.
3. Report pooled, station-specific, lead-specific and high-flow metrics against a persistence baseline. Here the pooled result improves while many individual stations and a substantial fraction of high-flow subsets do not.
4. Independently validate station coordinates, basin/routing relationships, high-flow events, data freshness and uncertainty.
5. Keep the LSTM map contribution optional and clearly marked experimental until station coordinates/routing, source freshness, uncertainty, and regional performance are independently reviewed. Do not turn the discharge percentile into flood-probability language.
6. Never treat missing input as zero, green/safe, or evidence of no flood. Official IMD, CWC and state disaster-management warnings remain authoritative.

## Research references

- CWC/NWIC river telemetry: https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc
- Open-Meteo Flood API / GloFAS context: https://open-meteo.com/en/docs/flood-api
- Google Research flood-forecasting implementation: https://github.com/google-research/flood-forecasting
- Caravan hydrological data reference: https://github.com/kratzert/Caravan
- HydroBASINS catchment polygons: https://www.hydrosheds.org/products/hydrobasins

Do not claim parity with Google Flood Hub. Its public open-source research code is not the entire production service. FloodWatch remains a research prototype and is not an official warning system.
