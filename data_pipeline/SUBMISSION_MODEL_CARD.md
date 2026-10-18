# FloodWatch ML / neural-network status card

Last repository review: 2026-10-18.

## Accurate status for a Datathon demo

FloodWatch has a reproducible **single-station discharge-only LSTM pilot** and a live end-to-end GitHub Actions training run. It is not yet an operational or validated South India flood-forecasting model.

| Capability | Status | Evidence |
|---|---|---|
| Local neural network architecture | Prototype code + guarded inference | `scripts/train_discharge_lstm.py` and `scripts/predict_discharge_lstm.py` implement a discharge-only PyTorch LSTM; `scripts/train_streamflow_lstm.py` is the separate weather-plus-discharge research path. |
| General ML event classifier | Prototype code exists | `scripts/train_event_ml.py` implements a scikit-learn classifier with chronological evaluation and a decision threshold selected on validation data only. |
| Trained local model / saved weights | Training workflow in progress; artifacts are run outputs | [Train FloodWatch discharge LSTM](../.github/workflows/train-discharge-lstm.yml) downloads CWC/NWDP discharge archives, normalizes source rows, trains a selected station, and uploads model/scalers/metrics as a temporary artifact. No weights are auto-deployed. |
| Historical measured training observations | Available for a research pilot; station/event review remains | The CWC/NWDP archive pipeline produces normalized historical discharge with source metadata and quality reports. The pilot uses a high-coverage Yadgir station record; it is not yet a curated multi-basin training corpus. |
| External river-flow forecast | Present in frontend | Open-Meteo Flood API / GloFAS model estimates, not a FloodWatch-trained NN and not a direct gauge observation. |
| Validated flood probability | Not available | No calibrated, out-of-time validation on verified South India flood events has been published. |

## Training strategy

1. Acquire source-linked, station-identified CWC/state water-level and discharge records. Preserve each measurement's unit, source URL, timestamp, station ID and data quality. The discharge-only LSTM workflow now automates the CWC/NWDP download and normalization for the first station experiment.
2. Build daily features from verified discharge plus rainfall/weather. Reanalysis products such as ERA5-Land must be labelled estimates, not gauge observations.
3. Train per-gauge or multi-gauge model only where enough continuous discharge history exists. A water-level series cannot be silently substituted for discharge.
4. Keep training/validation/test periods chronological. Compare the LSTM against a simple persistence baseline; report MAE/RMSE/NSE, skill versus persistence, and quantify missing-data coverage. Do not promote the model if it fails to beat the baseline.
5. Train a separate flood-event classifier only with reviewed positive and negative labels tied to cited event records. “No record found” is not automatically a negative flood label.
6. The discharge-only LSTM report compares against persistence and includes a peak-period diagnostic. Use `predict_discharge_lstm.py` only with matching weights/scalers and a complete recent history; stale observations are explicitly labelled. The weather-plus-discharge path uses `review_streamflow_model.py`. Neither path auto-deploys models. Publish and review a full model card before showing locally modelled estimates. Keep the GloFAS baseline separately labelled.

## Research baseline / references

- CWC/NWIC hourly river-level records: https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc
- Open-Meteo Flood API (GloFAS modelled discharge): https://open-meteo.com/en/docs/flood-api
- Google Research open flood-forecasting model implementations: https://github.com/google-research/flood-forecasting
- Caravan hydrological dataset / data-pipeline reference: https://github.com/kratzert/Caravan

**Do not claim parity with Google Flood Hub.** Its public open-source research implementation is not the entire production Flood Hub service. FloodWatch is a research prototype and is not an official warning system.
