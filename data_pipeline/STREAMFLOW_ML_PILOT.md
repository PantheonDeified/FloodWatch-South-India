# FloodWatch streamflow ML pilot

## What the neural network does

The pilot is a **single-gauge LSTM (Long Short-Term Memory) regression model**. It reads 90 days of aligned daily historical weather and observed river discharge and predicts the next 7 daily discharge values (m³/s). The horizon and lookback can be changed in the workflow inputs.

It is a research baseline, not Google's production Flood Forecasting model, and it does not currently predict flood probability, water depth, or inundation area. It also does not use future weather forecasts.

## Data required before training

The feature CSV must be produced and reviewed using the pipeline scripts. It must contain these columns:

- Identity/time: `station_id`, `date`
- Weather: `precipitation_sum`, `temperature_2m_mean`, `temperature_2m_max`, `temperature_2m_min`, `wind_speed_10m_max`
- Rainfall history: `rain_sum_3d_mm`, `rain_sum_7d_mm`, `rain_sum_14d_mm`, `rain_sum_30d_mm`
- Target: `river_discharge_last_m3s`

The target must be **observed river discharge in m³/s**. Do not train this model on river level, reservoir level, mixed measurement types, synthetic data, or records with unverified units. Check station identifiers, source URLs, timestamp semantics, coordinate provenance, missing intervals, and station/catchment mapping before training.

Keep raw archives and large data files out of Git when possible. For the current workflow, put a reviewed feature CSV in the repository at `data_pipeline/training_data/features.csv` or set the workflow's `features_path` to another repository-relative CSV path. Do not commit sensitive credentials.

## Run it

1. Open [Train and evaluate streamflow LSTM](../actions/workflows/train-streamflow-lstm.yml).
2. Choose **Run workflow**.
3. Set `station_id` to an exact identifier in the feature CSV.
4. Keep the default 90-day lookback and 7-day horizon for the first experiment.
5. Open the run and download the `floodwatch-lstm-...` artifact.

The workflow audits readiness, trains the LSTM with chronological train/validation/test splits, compares it against a persistence baseline (repeat the latest observed discharge), applies a review gate, and uploads the report/model/scalers. It intentionally does not deploy the model automatically.

## Acceptance criteria

- At least 100 complete sequence windows and adequate train/validation/test windows.
- No silent filling of missing observations or calendar gaps.
- Normalization is fitted on training data only.
- Report includes MAE, RMSE, NSE, and persistence-baseline comparison on the held-out chronological test period.
- Do not present the model as useful unless it beats persistence on test RMSE and the result is reviewed across meaningful high-flow events.
- Passing a software gate is not proof of hydrological validity or a public-warning capability.

## Next scientific upgrades

1. Build a multi-gauge, basin-aware dataset with verified upstream connectivity.
2. Add forecast weather inputs from a documented provider and align issue time vs valid time to prevent leakage.
3. Evaluate event-based lead-time skill, uncertainty intervals, high-flow performance and seasonal transfer.
4. Compare LSTM with persistence, linear/ridge and tree-based baselines before choosing the final architecture.
5. Only after validation, integrate outputs into the map as clearly labelled experimental discharge estimates, not official warnings.
