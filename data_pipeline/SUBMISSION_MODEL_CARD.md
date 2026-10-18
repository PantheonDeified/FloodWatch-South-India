# FloodWatch ML / neural-network status card

Last repository review: 2026-10-18.

## Accurate status for a demo

FloodWatch has a completed experimental single-station LSTM pilot and a completed regional multi-station discharge LSTM training run, including a saved-weight inference smoke test. A subsequent review found that the earlier trainer accepted Goa and Puducherry as well as the five core states, and that the resulting inference output was a stale historical replay rather than live. The trainer has now been restricted to Andhra Pradesh, Karnataka, Kerala, Tamil Nadu and Telangana, the downloader requests the current calendar year, and a fresh run has been queued on the feature branch. Neither model is validated for public flood warnings, and neither model is connected to or deployed on the public map.

| Capability | Status | Evidence |
|---|---|---|
| Regional neural-network weights | Trained artifact exists | [Regional training run #39124572229 (earlier broader-scope experiment)](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39122959850), artifact floodwatch-regional-lstm. |
| Regional model evaluation | Completed on chronological holdout | 89,824 pooled test targets; LSTM RMSE 830.45 m³/s vs persistence 700.88 m³/s (18.5% worse pooled RMSE). This aggregate hides substantial station-level variance. |
| Per-station robustness | Mixed; not a pass for deployment | 99 of 218 tested stations beat persistence on RMSE. Only 60 of 116 comparable high-flow station subsets with a comparable baseline beat persistence on high-flow RMSE. |
| Reproducible inference | Predictor script and workflow smoke-test step added on feature branch | data_pipeline/scripts/predict_regional_lstm.py uses the saved weights, saved scaling values and an eligible 90-day history. Re-check the latest workflow run before treating the smoke test as passed. |
| Single-station neural-network pilot | Previously trained | Yadgir station holdout RMSE was 1,043.61 m³/s vs persistence 1,274.75 m³/s; high-flow NSE was −0.013, so extreme-flow reliability remains weak. |
| ML event classifier | Prototype code exists | data_pipeline/scripts/train_event_ml.py implements a scikit-learn classifier with chronological evaluation. It needs reviewed event labels before flood-event claims. |
| Calibrated flood probability / inundation map | Not available | Neither discharge LSTM estimates flood probability, water depth, inundation extent, evacuation routes nor household impact. |

## Regional training configuration and metrics

The earlier broader-scope run used a 90-day input history, seven-day forecast horizon, a 48-unit single-layer LSTM, batch size 512, a maximum of six epochs, early-stopping patience two and two CPU threads. Training itself took about 48 seconds after acquisition and normalization; total workflow wall-clock time is longer because official archive retrieval and normalization precede training. The cited metrics below are provisional historical-baseline results from the broader seven-region state filter, not the definitive five-state run.

| Pooled chronological test metric | Regional LSTM | Persistence baseline |
|---|---:|---:|
| MAE (m³/s) | 93.46 | 106.03 |
| RMSE (m³/s) | 1,121.33 | 2,079.66 |
| NSE | 0.343 | −1.261 |
| Test targets | 92,015 | 92,015 |

The latest five-state report used 241 source station IDs and produced usable forecast windows for 231. Its source calendar ended on 2026-10-17. Input timestamp age is a freshness heuristic only; it does not independently verify real-time sensor transmission. The holdout spans from 2016-11-07 to the end of the available source period. Test windows are sampled across stations rather than exhaustive. Source station metadata and coordinate identity need additional audit. Pooled RMSE skill is not proof that most stations improve: only 107 of 223 test stations beat persistence on RMSE, and 63 of 119 comparable high-flow station subsets beat their baseline. Review each station and high-flow counts before making performance claims.

Interpretation: the model is a meaningful training milestone, not an operational flood-prediction model. A physical discharge value, a station-relative high-flow threshold and an official flood-warning level are distinct concepts.

## Current five-state retraining

The latest feature-branch workflow uses exactly Andhra Pradesh, Karnataka, Kerala, Tamil Nadu and Telangana. It requests archive data through the current UTC calendar year and uses a versioned same-day cache. Workflow: https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/train-regional-lstm.yml. Do not use the prior seven-state pooled metrics as final five-state performance. The rerun must complete training, inference, and artifact upload; its report must be re-reviewed for station counts, input dates and per-station/high-flow performance. A successful smoke test on observations older than three days must remain labelled historical, not live.

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
