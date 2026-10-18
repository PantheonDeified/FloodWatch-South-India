# FloodWatch streamflow ML pilot

## What is implemented

FloodWatch now has a reproducible **single-station LSTM neural-network training workflow** that downloads CWC/NWDP historical river-discharge archives, normalizes the source rows with provenance, trains a PyTorch model, and evaluates it on a later chronological test period.

The first version uses the previous 90 days of **daily maximum observed river discharge** to predict the next 7 daily maxima. This makes it possible to start neural-network experiments without pretending that the current 407-record snapshot is a training dataset or waiting for rainfall/weather data to be spatially matched. It is an initial autoregressive baseline, not the final flood forecasting system.

## Run it

1. Open [Train FloodWatch discharge LSTM](../actions/workflows/train-discharge-lstm.yml).
2. Select **Run workflow**.
3. The default station is `karnataka|yadgir|16.73750000|77.12527778`, chosen because the current station audit shows a long, high-coverage record. You can select another exact station ID from the generated audit.
4. Keep the 90-day lookback, 7-day horizon and 80 maximum epochs for the first run.
5. Download the run artifact containing the trained model, scalers, metrics report and data-quality report.

The model artifacts are not automatically committed or deployed. The workflow can take several minutes because it downloads and normalizes the historical archive before training.

## Model and evaluation

- Architecture: one-layer PyTorch LSTM followed by a dense multi-output head.
- Inputs: previous daily maximum observed discharge only; no weather features in this first experiment.
- Target: daily maximum discharge in m³/s, preserving higher observations when a source has multiple readings on a calendar day.
- Missing calendar days remain missing. Sequence windows containing gaps are excluded rather than interpolated or zero-filled.
- The chronological split is 70% training, 15% validation and 15% testing by calendar time. Scaling is fitted on training windows only.
- Test metrics include MAE, RMSE, Nash–Sutcliffe efficiency (NSE), and a persistence baseline that repeats the latest observed discharge for all forecast days.
- A peak-period diagnostic is included using the 90th percentile of the training targets. This is a model diagnostic, **not** an official flood threshold.

## Important limitations

This is a research model, not Google's production Flood Forecasting model. It does not currently predict rainfall-driven runoff, flood probability, water depth, inundation extent, or official warnings. It must not be presented as operational until the source station, units and event periods are reviewed and it demonstrates skill on independent high-flow events. Station timestamps are kept as reported because source timezone semantics are unspecified.

The downloaded CWC archives include gaps and duplicate observations. The normalization and station audit reports must be reviewed alongside the model metrics. Good average RMSE alone is not sufficient if peak-flow performance is poor.

## Next ML milestones

1. Run the first station experiment and inspect the report and peak-period metrics.
2. Train at several stations across Krishna, Cauvery, Godavari and west-flowing basins; compare against persistence and simpler ML baselines.
3. Add historical rainfall aligned to verified station coordinates and valid times; later add forecast rainfall from a documented forecast source.
4. Build a multi-gauge/basin-aware model and evaluate flood-event recall, lead-time skill and uncertainty.
5. Only after independent validation, show experimental estimates on the map with clear provenance and status labels.

## Inference after training

After downloading the artifact and preparing a normalized observations CSV with the same station IDs, run the matching inference script:

```bash
python data_pipeline/scripts/predict_discharge_lstm.py \\
  --observations data_pipeline/output/cwc_discharge_normalized.csv \\
  --station-id "karnataka|yadgir|16.73750000|77.12527778" \\
  --model data_pipeline/output/models/discharge_lstm_karnataka_yadgir_16.73750000_77.12527778.pt \\
  --scalers data_pipeline/output/models/discharge_lstm_karnataka_yadgir_16.73750000_77.12527778.scalers.npz \\
  --output data_pipeline/output/experimental-discharge-forecast.csv
```

The script refuses a missing value in the most recent lookback window and writes a metadata sidecar that labels stale observations. Predictions should not be displayed as live unless the last observation is recent and the model has passed independent event validation.
