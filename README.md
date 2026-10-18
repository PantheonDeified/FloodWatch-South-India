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

The public NWDP/NWIC collector has completed a successful run. Its snapshot generated at `2026-10-17T23:12:45Z` contained **407 station/measurement records from 37 resource files**: 201 river-discharge, 145 river-level, 44 reservoir-level, 9 reservoir-storage and 8 reservoir/regulator-discharge records. This is evidence that the pipeline can produce real source-linked records; it is **not** proof of a complete or fully real-time river/dam network.

Known limitations: 34 records have no coordinates; 15 records are labelled Maharashtra, Chhattisgarh or Madhya Pradesh rather than the five core states; and some public resources have no usable rows or older reported timestamps. The collector preserves source timestamps but source timezone semantics are not specified, and hourly telemetry differs from manual/daily resources. Check each record's source, observation timestamp, unit and freshness before interpreting it.

See [Water pipeline run report](docs/water-pipeline-run-report.md) for the observed counts, workflow evidence and remaining quality checks.

Workflow: `.github/workflows/refresh-water-observations.yml`

To run it manually, open the repository's **Actions** tab, choose **Refresh official water observations**, and select **Run workflow**. Scheduled runs are configured every six hours. The workflow now refuses to publish an empty or inconsistent observation snapshot and no longer triggers itself solely because it committed the generated snapshot. A successful job still requires checking source timestamps, units, coordinates and resource-level errors.


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

## Optional IBM LinuxONE backend connection

The FastAPI service exposes `/health` and `/api/v1/status`; the versioned source is in [backend/main.py](backend/main.py). It also contains `GET /api/v1/weather?latitude=19.15&longitude=77.30`, a source-labelled proxy to Open-Meteo current conditions and hourly forecasts for the supported South India area.

The frontend can try the backend weather endpoint when an HTTPS API base URL is configured in the current browser. If the endpoint is unavailable or not yet deployed, it falls back to the existing direct Open-Meteo request and labels that fallback. Follow [backend deployment instructions](backend/README.md) to update the IBM LinuxONE process to the versioned source, then use the website's backend connection panel to verify connectivity.

The temporary connection panel is a developer tool, not part of the intended final user experience. It stores the URL in the current browser's local storage, not in the public repository. The Quick Tunnel URL may change and has no uptime guarantee; do not treat it as production hosting, and never expose secrets or private data through this demo API. The backend does not yet aggregate all flood datasets or serve a validated FloodWatch flood forecast.

## Publish with GitHub Pages

1. Open the repository **Settings → Pages**.
2. Select **Deploy from a branch**.
3. Choose branch `main` and folder `/(root)`, then save.
4. Wait for GitHub Pages to finish publishing.


## ML and neural-network status — important for demos

- **Model code exists:** a PyTorch LSTM research training script for a verified discharge gauge and a scikit-learn flood-event classifier with chronological evaluation.
- **Not yet operational:** no published trained South India model weights or validated local forecasts; the water-observation data exists, but source freshness, station coverage and historical inputs still require quality checks.
- **Current river-flow outlook:** the website can request modelled GloFAS flow estimates via Open-Meteo. This is an external forecast, not a FloodWatch-trained neural network or a live CWC gauge reading.
- **No validated local flood probabilities or depth maps are currently claimed.**

See [ML / neural-network model card](data_pipeline/SUBMISSION_MODEL_CARD.md) for exact status, training requirements and scientific guardrails.

