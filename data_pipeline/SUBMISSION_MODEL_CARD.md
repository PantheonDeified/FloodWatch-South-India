# FloodWatch ML / neural-network status card

Last repository review: 2026-10-18.

## Accurate status for a Datathon demo

FloodWatch has **ML training code under development**, but does not yet have an operational, locally trained South India flood-forecasting model.

| Capability | Status | Evidence |
|---|---|---|
| Local neural network architecture | Prototype code exists | `scripts/train_streamflow_lstm.py` implements a PyTorch LSTM for daily discharge; `scripts/predict_streamflow_lstm.py` provides guarded inference after training. |
| General ML event classifier | Prototype code exists | `scripts/train_event_ml.py` implements a scikit-learn classifier with chronological evaluation and a decision threshold selected on validation data only. |
| Trained local model / saved weights | Not verified; not supplied in the repository | No model artifact or completed evaluation report is published. |
| Verified measured training observations | Not yet sufficient / not verified | `data/water-observations.json` is an operational snapshot, not a curated historical training table. Training also requires normalized daily discharge or reviewed flood-event labels. |
| External river-flow forecast | Present in frontend | Open-Meteo Flood API / GloFAS model estimates, not a FloodWatch-trained NN and not a direct gauge observation. |
| Validated flood probability | Not available | No calibrated, out-of-time validation on verified South India flood events has been published. |

## Training strategy

1. Acquire source-linked, station-identified CWC/state water-level and discharge records. Preserve each measurement's unit, source URL, timestamp, station ID and data quality.
2. Build daily features from verified discharge plus rainfall/weather. Reanalysis products such as ERA5-Land must be labelled estimates, not gauge observations.
3. Train per-gauge or multi-gauge model only where enough continuous discharge history exists. A water-level series cannot be silently substituted for discharge.
4. Keep training/validation/test periods chronological. Compare the LSTM against a simple persistence baseline; report MAE/RMSE/NSE, skill versus persistence, and quantify missing-data coverage. Do not promote the model if it fails to beat the baseline.
5. Train a separate flood-event classifier only with reviewed positive and negative labels tied to cited event records. “No record found” is not automatically a negative flood label.
6. Run `review_streamflow_model.py` to reject candidates that fail the persistence benchmark or lack evaluation artifacts; passing only allows human review, never automatic deployment. Use `predict_streamflow_lstm.py` only with a matching trained model/scaler and complete recent feature window. Publish a model card and evaluation report before showing forecasts as locally modelled. Keep the GloFAS baseline separately labelled.

## Research baseline / references

- CWC/NWIC hourly river-level records: https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc
- Open-Meteo Flood API (GloFAS modelled discharge): https://open-meteo.com/en/docs/flood-api
- Google Research open flood-forecasting model implementations: https://github.com/google-research/flood-forecasting
- Caravan hydrological dataset / data-pipeline reference: https://github.com/kratzert/Caravan

**Do not claim parity with Google Flood Hub.** Its public open-source research implementation is not the entire production Flood Hub service. FloodWatch is a research prototype and is not an official warning system.
