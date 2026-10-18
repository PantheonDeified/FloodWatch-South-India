# FloodWatch vs Google Flood Hub — engineering gap analysis

Last checked: 2026-10-18. This is a feature and readiness comparison, not a claim of equivalent forecast skill.

## What Google Flood Hub publicly documents

Google's public product combines a riverine hydrology forecast model and a separate inundation mapping model. It publishes riverine forecasts up to seven days ahead, water trends, flood status/alerts and local inundation information where coverage is available. Google also documents a separate 24-hour flash-flood forecast for covered urban and rural areas. Reference pages:
- Product overview: https://support.google.com/flood-hub/answer/15636593?hl=en
- Model overview: https://support.google.com/flood-hub/answer/15638002?hl=en
- Flash-flood model: https://support.google.com/flood-hub/answer/16811681?hl=en
- API and historical datasets: https://developers.google.com/flood-forecasting
- Open hydrology implementation: https://github.com/google-research/flood-forecasting

## Current FloodWatch readiness

| Capability | FloodWatch status | What is still required |
|---|---|---|
| Interactive map / location search | Implemented as a frontend prototype | Usability, error and accessibility testing at more locations/devices. |
| Current weather and short-range point forecast | Implemented using Open-Meteo | It is gridded weather-model output, not a local rain gauge or river measurement. |
| Historical rainfall analysis | Browser code and historical API integration are present | Run live end-to-end tests, confirm dataset freshness and check seasonal calculations at multiple South Indian locations. |
| Modelled river discharge context | Open-Meteo Flood API request and interpretation panel are present | Validate which GloFAS grid cell is returned, separate reanalysis/past estimates from forecast days, test availability and avoid treating a clicked point as a named river reach. |
| Official river/dam/reservoir observations | Source collector, registry, GitHub Actions workflow and frontend snapshot reader have been added | The collector has successfully published a non-empty snapshot: 407 records from 37 resource files in the 2026-10-18 run. Public datasets may lack coordinates, timestamps can be ambiguous, and station/asset coverage is incomplete. This is not yet a verified all-South-India live feed; per-source freshness and geography still need auditing. |
| Historical station observations | Normalization scripts and source links exist | Download actual CWC/NWDP resources and verify columns, units, station IDs, time zones, actual date ranges, missingness and data licensing. No complete historic station archive has been ingested into the product yet. |
| Gauge-to-catchment mapping | HydroBASINS assignment script exists | Need a verified station catalog, basin polygon data and reviewed channel/flow direction connections. The script's candidate mappings are not ground-truth connections. |
| Rain → antecedent conditions → river response evidence | Frontend evidence-chain panel and feature-building script exist | Need verified station observations, connected upstream catchments, validated thresholds and labelled historical events. The current chain is contextual evidence, not a calibrated flood prediction. |
| ML river-flow forecast trained on South Indian data | **Not implemented/validated** | Training script is only a research pilot. Need suitable discharge training records, basin attributes, aligned forcing data, chronological splits and independent validation. |
| ML flood-event / flash-flood probability | **Not implemented/validated** | Classifier script requires independently reviewed event labels and valid non-event samples. No flood-probability score is currently trustworthy for public display. |
| Google-style hydrology architecture | Not integrated | OpenHydroNet must run in a Python backend/compute environment with dependencies and trained weights. GitHub Pages browser code cannot run the PyTorch hydrology model as it stands. |
| Inundation depth / affected-area maps | **Not implemented** | Needs a validated inundation model, terrain/river geometry, relevant hydrologic forecasts and historical flood footprints. Rainfall/rain radar alone cannot produce a valid flood extent. |
| Flash-flood forecasts up to 24 hours | **Not implemented** | Requires a separately trained/validated spatial model and trustworthy event labels; river-gauge forecasts cannot stand in for this. |
| Gauge-side panel / forecast hydrograph and confidence metadata | Partial only | Need station-specific observed history, forecasts by lead day, official severity thresholds and clearly stated uncertainty/confidence. |
| Alerts, subscriptions and notification channels | **Not implemented** | Need server-side monitoring, well-defined triggers, reliable delivery and coordination with official warnings. |
| Spatial event/coverage maps across South India | **Not implemented** | Need a spatial forecast product with declared coverage and calibrated outputs; current selected-point data are not a continuous flood-risk surface. |
| Public API / data exports | **Not implemented** | Need a versioned backend with provenance, authentication if required, rate limits, schema and monitoring. |

## Critical differences from Google

### 1. Streamflow versus water level
Google's open hydrology model predicts streamflow. Many Indian CWC/NWDP resources provide water levels in metres. Those quantities are not interchangeable. A station-specific rating curve, applicable period and uncertainty are needed before converting water level into discharge. Do not relabel a water-level series as cubic metres per second.

### 2. Spatial watershed context
A map coordinate needs to be tied to the relevant upstream catchment and river reach. Straight-line distance to a gauge or dam is not enough: flow direction, tributaries, reservoirs, diversions and gauge position matter.

### 3. Model skill and calibration
FloodWatch currently has no South-India-trained model with demonstrated out-of-time event skill. Before showing public flood probabilities, test against held-out years and flood events; report per-basin performance, peak timing, false alarms and missed events, and document regions with insufficient data.

### 4. Data availability versus physical coverage
“Every river and dam” cannot honestly be promised from public records. Some facilities have only manual daily records, some are unlocated or inaccessible, and many have no public continuously updated data feed. FloodWatch should show exactly which sources, stations and timestamps are available and make gaps explicit.

## Suggested implementation sequence

1. **Make the station snapshot collector run reliably.** Verify actual source CSV links and headers and review the first successful run; expose resource errors rather than claiming a successful live feed by schedule alone.
2. **Build the verified gauge/asset catalog.** Source coordinates and station IDs only from official records; keep source URL, unit, observation type and datum/rating-curve metadata.
3. **Ingest historical records.** ERA5-Land daily meteorological reanalysis is available from 1950 onward; NWDP/CWC portal resources include station-specific periods such as 1961–1990, 1991–2020, 2021–2025 and 2026–2030 where published. Actual station coverage must be calculated from downloaded data.
4. **Map gauges to catchments and river-network candidates.** Review the results against actual river flowlines and engineering metadata.
5. **Create a curated rain/river/flood-event training set.** Include verified source-linked events and non-events, and don't assume an unreported day is a flood-free day.
6. **Benchmark before ML.** Compare climatology/persistence and public hydrology products, then train an LSTM/other candidate and evaluate out of time and on held-out basins.
7. **Add riverine forecast service.** Version the model, inputs, issue time, valid time, horizon, uncertainty and data quality; serve predictions from a backend.
8. **Add inundation and flash-flood models separately.** They have different inputs, target labels and spatial validation needs.
9. **Operationalize warnings responsibly.** Distinguish official warnings from model signals; monitor feed freshness and provide direct IMD/CWC/state-authority links.

## Sources

- Google Flood Hub overview: https://support.google.com/flood-hub/answer/15636593?hl=en
- Google model overview: https://support.google.com/flood-hub/answer/15638002?hl=en
- Flash-flood model: https://support.google.com/flood-hub/answer/16811681?hl=en
- Google Flood Forecasting API / GRRR / inundation history: https://developers.google.com/flood-forecasting
- OpenHydroNet code: https://github.com/google-research/flood-forecasting
- CWC/NWDP telemetry: https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc
- Historical weather API: https://open-meteo.com/en/docs/historical-weather-api
- Flood API: https://open-meteo.com/en/docs/flood-api
