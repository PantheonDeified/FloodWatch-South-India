# FloodWatch South India

An independent, browser-based flood situational-awareness research prototype for South India, inspired by the public capabilities of Google Flood Hub.

## Website

Expected GitHub Pages URL: https://pantheondeified.github.io/FloodWatch-South-India/

## Current frontend capabilities

- Interactive Leaflet map with street, terrain and satellite basemaps.
- Place search, map-click selection, coordinate entry and optional browser geolocation.
- Point weather conditions and an hourly forecast from Open-Meteo. These are gridded model estimates, not direct observations at every location.
- RainViewer radar overlay with a displayed source timestamp and a freshness check.
- Historical rainfall comparisons using ERA5-Land reanalysis, including a 1991–2020 baseline, latest complete monthly totals, a rolling 7-day seasonal percentile and a month-to-date anomaly where records are complete.
- Modelled river-discharge context and short-range outlook from the Open-Meteo Flood API / GloFAS. This is modelled discharge, not a CWC gauge reading or a measured river height.
- Official river/reservoir observation table interface, filters, and a rainfall-to-river evidence chain. The interface reads `data/water-observations.json`.
- Official IMD/CWC/NDMA source links and clear limitations.

## Important live-data status

A collector and a GitHub Actions workflow have been added for selected public NWDP/NWIC river-level, discharge and reservoir resources. **The current committed snapshot remains empty until a workflow run successfully downloads and validates records.** Therefore, this repository should not yet be described as providing a verified live river/dam network. The collector can only cover resources found on its configured public source pages; some station records are manual/daily, some lack usable coordinates, and public records do not cover every physical river or dam.

Workflow: `.github/workflows/refresh-water-observations.yml`

To run it manually, open the repository's **Actions** tab, choose **Refresh official water observations**, and select **Run workflow**. Inspect the run logs and the generated `data/water-observations.json`. A successful job is not enough by itself: verify that station counts, source timestamps and data-quality reports are plausible before relying on the values. Scheduled runs are configured every six hours, but an empty snapshot or a failed source is never replaced with guessed readings.

## Historical data and model research

- `data_pipeline/scripts/fetch_historical_weather.py`: fetches daily ERA5-Land weather reanalysis (available from 1950) at explicitly verified station coordinates.
- `data_pipeline/scripts/inspect_cwc_csv.py` and `normalize_cwc_levels.py`: inspect and normalize downloaded official CWC/NWDP CSVs while preserving source provenance and units.
- `data_pipeline/scripts/assign_gauges_to_basins.py`: candidate gauge-to-HydroBASINS mapping using verified coordinates and upstream/downstream basin IDs. Results require human river-network validation.
- `data_pipeline/scripts/build_event_features.py`: builds lagged rainfall and river-response features without filling missing observations with zero.
- `data_pipeline/scripts/train_streamflow_lstm.py`: research-only single-station streamflow LSTM pilot; requires actual discharge data, not water-level values mislabeled as discharge.
- `data_pipeline/scripts/train_event_ml.py`: baseline classifier for source-linked, reviewed flood-event labels; no reliable model can be trained without a suitable labelled dataset.
- `MODEL_ADAPTATION.md`: model architecture and adaptation/evaluation plan.
- `FLOOD_HUB_GAP_ANALYSIS.md`: comparison against Google's published Flood Hub capabilities and the remaining work.

Official historical records are available for some river groups over periods such as 1961–1990, 1991–2020 and newer periods. ERA5-Land gives a consistent meteorological reanalysis from 1950. These periods are not a promise of complete data at every station: each downloaded file must be checked for actual row dates, missingness, units and station identity.

## What is not implemented/validated yet

FloodWatch does **not** yet have a South-India-trained production hydrology model, calibrated local flood probabilities, verified upstream/downstream gauge connectivity, a validated inundation-depth/extent model, a separate 24-hour flash-flood model, a complete all-dam real-time feed, or alert notifications. The evidence-chain panel describes available context; it is not an official flood warning and does not claim that rain alone causes a flood.

Google's open-source hydrology framework is a research starting point, not a ready-to-run Google Flood Hub production service. The model should be trained and evaluated on well-aligned South Indian basin data, tested on held-out years/events and compared with transparent baselines before any forecast is published.

## Safety and attribution

This is an independent project, not affiliated with or endorsed by Google Flood Hub. It must not be used as the sole basis for emergency decisions. Follow official IMD, CWC and state disaster-management warnings. External data and map providers retain their own licensing/attribution requirements.

## Publish with GitHub Pages

1. Open the repository **Settings → Pages**.
2. Select **Deploy from a branch**.
3. Choose branch `main` and folder `/(root)`, then save.
4. Wait for GitHub Pages to finish publishing.


## ML and neural-network status — important for demos

- **Model code exists:** a PyTorch LSTM research training script for a verified discharge gauge and a scikit-learn flood-event classifier with chronological evaluation.
- **Not yet operational:** no published trained South India model weights or validated local forecasts; the public water-observation snapshot has to populate and historical data must be cleaned first.
- **Current river-flow outlook:** the website can request modelled GloFAS flow estimates via Open-Meteo. This is an external forecast, not a FloodWatch-trained neural network or a live CWC gauge reading.
- **No validated local flood probabilities or depth maps are currently claimed.**

See [ML / neural-network model card](data_pipeline/SUBMISSION_MODEL_CARD.md) for exact status, training requirements and scientific guardrails.

