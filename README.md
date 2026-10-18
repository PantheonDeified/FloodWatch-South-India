# FloodWatch South India

An independent, browser-based flood situational-awareness research prototype for South India, inspired by the public capabilities of Google Flood Hub.

## Website

Expected GitHub Pages URL: https://pantheondeified.github.io/FloodWatch-South-India/

Full feature matrix: [FloodWatch capabilities and implementation status](docs/FEATURES_AND_CAPABILITIES.md).

New: [Problems solved, early-warning workflow and infrastructure accountability](docs/EARLY_WARNING_AND_ACCOUNTABILITY.md).

## Backend and ML status

The FastAPI backend is in `backend/`. It includes health/status endpoints, the Open-Meteo weather proxy, a paginated `/api/v1/water-observations` endpoint, and `/api/v1/models/status`. The water endpoint can read a local snapshot or fetch the public repository snapshot. Updating files in GitHub does **not** automatically update the separately running Linux API service; follow [backend deployment notes](backend/README.md).

### Verified experimental model status (18 October 2026)

A **single-station discharge LSTM has successfully trained and completed a chronological holdout evaluation** using CWC/NWDP-derived daily maximum discharge for the Yadgir station in Karnataka. Its downloadable weights, scaler file, and JSON evaluation report are attached to [GitHub Actions training run #39115932750](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39115932750) as artifact `floodwatch-discharge-lstm-6` (artifact retention is temporary). The report shows overall test RMSE **1,043.61 m³/s** versus **1,274.75 m³/s** for persistence, an 18.1% reduction. High-flow subset NSE is **−0.013**, so extreme-flow skill remains weak. This is one station only, not a South India-wide forecast.

The separate [regional multi-station LSTM workflow](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/train-regional-lstm.yml) is experimental and must be evaluated from its own final report before any regional metric is claimed. Its training settings use a 90-day lookback, 7-day forecast horizon and a seven-day stride to bound memory use. The model currently uses historical discharge, observation masks, calendar seasonality and station coordinates; it does **not** ingest rainfall/weather forecasts or produce flood probabilities, depth or inundation extent.

**These trained weights are not yet integrated into the live website/API.** The website's river-flow outlook is separately labelled external Open-Meteo Flood API/GloFAS model data. Do not confuse that feed with the local LSTM.

See [verified ML metrics and code tests](docs/ML_VALIDATION_SNAPSHOT.md), [ML upgrade plan](docs/ML_UPGRADE_PLAN.md), and the [model card](data_pipeline/SUBMISSION_MODEL_CARD.md).

## Problems FloodWatch targets

- **Fragmented flood information:** brings weather, radar, river-flow model context, public water observations and official warning links into one map-led workflow.
- **Late awareness:** helps users notice changing rainfall/river conditions and quickly reach the relevant official advisory.
- **Data uncertainty:** exposes source timestamps, provenance and known limitations so stale or modelled data are not mistaken for direct observations.
- **Human factors in flood impact:** a browser-local evidence notebook lets a user record source-linked public documents about reservoir operations, inspections, embankments, drainage maintenance, floodplain changes and warning/response timelines. It is not a shared or automatically verified public register.

## How early warning should work

1. Ingest timestamped rainfall forecasts/observations, radar, river gauges, published reservoir updates, cyclone advisories and official warnings.
2. Validate units, station identity, source and freshness. A stale feed means **risk unknown**, not safe.
3. Combine multiple signals with locally validated hydrological models; never use a neural network as the sole authority.
4. Use locally approved thresholds tested against historical events, and clearly distinguish a modelled watch from an official warning.
5. After authorization and end-to-end testing, alerts could be sent by opt-in web/app/SMS/email with location, issue time, evidence, uncertainty, official guidance and source links.
6. Evaluate lead time, missed events, false alarms, delivery success and correction/cancellation handling.

## Human-made infrastructure and accountability

The dashboard now includes a **browser-local infrastructure evidence notebook**. Each user-entered record can include a public source URL, place, issuing agency, document date, review status and notes; users can export the entries as JSON. These notes stay in that browser and are not sent to a shared server. A future shared evidence register would still need verified source ingestion, reviewer identities, change history, corrections, access controls and safeguards against publishing sensitive infrastructure details.

**Important safeguards:** reservoir level alone cannot establish structural strength; this requires qualified engineering assessment and competent-authority records. A release occurring before a flood does not by itself prove causation. Distinguish unverified reports from agency-confirmed facts, avoid unsupported accusations, and do not publish sensitive infrastructure-security information.

**Current boundary:** map/weather/radar/wind/cyclone context, historical rainfall context, external modelled river-flow context, public water-observation exploration, the NRSC/ISRO historical flood-evidence overlay (Andhra Pradesh hazard zonation plus aggregated historical inundation maps for Karnataka, Kerala and Tamil Nadu), the GDACS cyclone-event risk overlay, data-quality pipeline and experimental discharge LSTMs exist in the project. The new 0.5° FloodWatch-calculated grid independently scores raw 24/72-hour rain forecasts, rain probability, current precipitation, recent GloFAS discharge percentiles and fresh nearby gauge-history signals. It is provisional, not calibrated flood probability; grey means missing data, while original rain radar and other source overlays remain independent. NRSC's portal describes the hazard atlas as built by integrating maximum inundation layers from 1998–2019 and its aggregated state maps as satellite-derived historic flood maps from 2003–2020; those products should not be treated as equivalent risk scores. Telangana coverage in the selected NRSC WMS service is not verified and is explicitly treated as unknown. Automated geofenced alert delivery and a shared/server-side infrastructure evidence register are not yet implemented. Open-Meteo/GloFAS forecasts are external model products, not predictions from FloodWatch's LSTM.

See the [early-warning and accountability design](docs/EARLY_WARNING_AND_ACCOUNTABILITY.md) for the intended workflow and limitations.

## FloodWatch calculated regional risk grid

The map now opens with a **South India-wide, 0.5° grid**. Each cell's own provisional score is calculated from raw inputs—not another website's red/amber/green labels:

- 40% weight: forecast rain over 24 hours (100 mm saturates this component).
- 30%: forecast rain over 72 hours (150 mm saturates this component).
- 15%: maximum forecast rain probability over 24 hours.
- 15%: current modelled precipitation rate (20 mm/h saturates this component).
- Where available, the seven-day GloFAS discharge peak is compared against up to 92 preceding days at that grid point and blended with the rainfall score (75% rainfall / 25% discharge). A fresh nearby river gauge may raise the score using its own historical percentile and rise trend.

**Colours:** red ≥65, amber ≥35, green <35; grey means data are missing/insufficient. The score is a short situational-awareness indicator, **not a calibrated flood probability or an official warning**. Thresholds are provisional project-defined settings and still require event-based calibration; the 92-day flow comparison is not seasonally normalized. Nearby gauges are not assumed to be upstream-connected. Grid boundaries use simplified regional polygons and border cells are approximate. Popups show the underlying values. Existing rain radar, cloud, wind, station and historic-flood layers remain available independently.

Source numerical fields: [Open-Meteo weather API](https://open-meteo.com/en/docs) and [Open-Meteo Flood API / GloFAS](https://open-meteo.com/en/docs/flood-api); public station context from the repository's NWDP/NWIC/CWC-derived snapshot. Data sources provide the observations/model outputs; **FloodWatch calculates the colour itself**.

## Current frontend capabilities

- Interactive Leaflet map with street, terrain and satellite basemaps.
- Place search, map-click selection, coordinate entry and optional browser geolocation.
- Point weather conditions and an hourly forecast from Open-Meteo. These are gridded model estimates, not direct observations at every location.
- RainViewer radar overlay with a displayed source timestamp and a freshness check.
- **Risk-map selector** beside the base-map selector: the NRSC/ISRO historical flood-hazard WMS can be overlaid on any existing base map; GDACS source-alert cyclone features can be shown separately or combined with historical flood hazard. NRSC's native layer colours are preserved rather than recoloured by guesswork. The WMS MapCache legend endpoint returns HTTP 501, so the in-map panel links to the official atlas for interpreting exact colour classes. These are historical mapped hazard classes, not guaranteed safety or current flood probability. Verified WMS layers are Andhra Pradesh's hazard-zonation layer plus Karnataka/Kerala/Tamil Nadu's aggregate historic flood maps (2003–2020); these are different evidence products, not one calibrated risk scale. Telangana remains unclassified/unknown in this service catalogue. Cyclone alerts use reported event geometry/alert levels only; FloodWatch does not invent storm-radius polygons.
- Spatial wind-direction/speed overlay sourced from Open-Meteo, and a GDACS tropical-cyclone event overlay with official IMD links as the warning fallback; these overlays require live browser verification after deployment.
- Historical rainfall comparisons using ERA5-Land reanalysis, including a 1991–2020 baseline, latest complete monthly totals, a rolling 7-day seasonal percentile and a month-to-date anomaly where records are complete.
- Modelled river-discharge context and short-range outlook from the Open-Meteo Flood API / GloFAS. This is modelled discharge, not a CWC gauge reading or a measured river height.
- Official river/reservoir observation table with search and filters for measurement type, source-reported freshness, and state label (the five core states, outside-core labels, or unspecified state). A coverage summary reports counts by state label and freshness category; state labels are source-provided, not independently verified from coordinates. An optional water-station map overlay plots only source records with usable coordinates inside the core map area, labels measurement types by color, and shows the source timestamp/link in each popup. The interface reads `data/water-observations.json`; markers are off by default and are not flood alerts.
- Official IMD/CWC/NDMA source links and clear limitations.

## Important live-data status

The public NWDP/NWIC collector completed a successful GitHub Actions run on 2026-10-18. Its snapshot generated at `2026-10-18T02:32:25Z` contained **407 station/measurement records from 37 resource files**: 201 river-discharge, 145 river-level, 44 reservoir-level, 9 reservoir-storage and 8 reservoir/regulator-discharge records. This is evidence that the pipeline can produce real source-linked records; it is **not** proof of a complete or fully real-time river/dam network.

Known limitations: 34 records have no coordinates; 15 records are labelled Maharashtra, Chhattisgarh or Madhya Pradesh rather than the five core states; and some public resources have no usable rows or older reported timestamps. The newest timestamp string currently reported is `2026-10-18T12:10:00` for Hemavathy Dam, which the page may label as a future timestamp depending on source timezone. The collector preserves source timestamps but timezone semantics are not specified, and hourly telemetry differs from manual/daily resources. Check each record's source, observation timestamp, unit and freshness before interpreting it.

See [Water pipeline run report](docs/water-pipeline-run-report.md) for the observed counts, workflow evidence and remaining quality checks.

Workflow: `.github/workflows/refresh-water-observations.yml`

To run it manually, open the repository's **Actions** tab, choose **Refresh official water observations**, and select **Run workflow**. Scheduled runs are configured every six hours. The workflow now refuses to publish an empty or inconsistent observation snapshot and no longer triggers itself solely because it committed the generated snapshot. A successful job still requires checking source timestamps, units, coordinates and resource-level errors. The workflow also regenerates `docs/water-pipeline-report.md` with counts, per-source timestamp strings, source-page/resource failures, observed unit labels and data-quality indicators. A separate fast CI workflow runs the water-pipeline unit tests, validates the committed snapshot, and checks that the audit report can be generated without downloading upstream datasets. The workflow also runs unit tests for `data_pipeline/scripts/validate_water_snapshot.py` and uses that validator to check record IDs, values, units, HTTPS source links, coordinates and timestamp warnings. Run the validator locally with `python data_pipeline/scripts/validate_water_snapshot.py --snapshot data/water-observations.json`.


## Historical data and model research

- `data_pipeline/scripts/fetch_historical_weather.py`: fetches daily ERA5-Land weather reanalysis (available from 1950) at explicitly verified station coordinates.
- `data_pipeline/scripts/inspect_cwc_csv.py` and `normalize_cwc_levels.py`: inspect and normalize downloaded official CWC/NWDP CSVs while preserving source provenance and units.
- `data_pipeline/scripts/assign_gauges_to_basins.py`: candidate gauge-to-HydroBASINS mapping using verified coordinates and upstream/downstream basin IDs. Results require human river-network validation.
- `data_pipeline/scripts/build_event_features.py`: builds lagged rainfall and river-response features without filling missing observations with zero.
- `data_pipeline/scripts/train_discharge_lstm.py`: trained single-station daily-discharge LSTM with chronological holdout evaluation against persistence; artifact available from the linked Actions run above.
- `data_pipeline/scripts/train_regional_lstm.py`: experimental multi-station, multi-horizon LSTM; report is accepted only after the regional workflow finishes and its own artifact is inspected.
- `data_pipeline/scripts/train_streamflow_lstm.py`: earlier research-only single-station streamflow LSTM pilot; requires actual discharge data, not water-level values mislabeled as discharge.
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

The frontend can try the backend weather endpoint when an HTTPS API base URL is configured in the current browser. If the endpoint is unavailable, it falls back to the direct Open-Meteo request and labels that fallback. Follow [backend deployment instructions](backend/README.md) to update the IBM LinuxONE process to the versioned source.

The backend connection panel is hidden from the normal public page. For temporary developer testing, open the [developer tools view](https://pantheondeified.github.io/FloodWatch-South-India/?devtools=1), paste the current HTTPS API base URL, and select **Test API**. The URL is stored only in that browser's local storage, not in the public repository. The panel is not part of the intended final user experience.

The Quick Tunnel URL may change and has no uptime guarantee; do not treat it as production hosting, and never expose secrets or private data through this demo API. The backend does not yet aggregate all flood datasets or serve a validated FloodWatch flood forecast.

## Publish with GitHub Pages

1. Open the repository **Settings → Pages**.
2. Select **Deploy from a branch**.
3. Choose branch `main` and folder `/(root)`, then save.
4. Wait for GitHub Pages to finish publishing.


## ML and neural-network status — important for demos

- **Model code exists:** a PyTorch LSTM training/inference path with persistence-baseline evaluation, a per-station readiness audit, and a scikit-learn flood-event classifier with validation-only threshold selection.
- **Training verified:** one Karnataka station LSTM has trained and been evaluated against persistence on a chronological holdout. See the linked training artifact and validation snapshot above.
- **Not yet operational:** the trained station model is not served by the live website/API, and no validated South India-wide forecast is claimed; source freshness, station coverage and historical inputs still require quality checks.
- **Current river-flow outlook:** the website can request modelled GloFAS flow estimates via Open-Meteo. This is an external forecast, not a FloodWatch-trained neural network or a live CWC gauge reading.
- **No validated local flood probabilities or depth maps are currently claimed.**

See [ML / neural-network model card](data_pipeline/SUBMISSION_MODEL_CARD.md) for exact status, training requirements and scientific guardrails. See the [historical-data pipeline guide](data_pipeline/README.md), [Flood Hub gap analysis](FLOOD_HUB_GAP_ANALYSIS.md), and [manual historical CWC discharge/rainfall download workflow](.github/workflows/download-historical-hydrology.yml) for the next data-ingestion steps.


## Project completion status

See [Project readiness and 100% acceptance gates](docs/project-readiness.md) for the six workstreams, current evidence, remaining blockers, and workflow runbooks. Scheduled deployed-site smoke checks are defined in `.github/workflows/production-smoke-check.yml` and monitor the published page and water-data snapshot. A successful check validates availability/schema/freshness only; it does not validate a flood forecast.
