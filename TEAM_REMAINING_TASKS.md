# FloodWatch South India — Single-Owner Remaining Tasks

The project lead is handling the tasks that were originally split between teammates. Use this file as the integrated checklist; do not wait for separate teammate reports.

## Implemented in the repository

- Interactive Leaflet map with street, terrain and satellite basemaps.
- Place search, map-click selection, coordinate entry, and optional browser geolocation.
- Open-Meteo current conditions and hourly forecast; ERA5-Land historical rainfall comparisons; Open-Meteo Flood API/GloFAS modelled river-discharge context.
- RainViewer radar and Open-Meteo spatial cloud-cover overlay.
- Public NWDP/NWIC observation collector, source registry, six-hour GitHub Actions workflow, snapshot validator, tests, and frontend table/map reader.
- Successful water collector run produced 407 records from 37 resource files across 20 configured source pages. This is not proof every source is fresh or complete.
- FastAPI backend source with health/status, weather proxy, GloFAS river-flow proxy, paginated water-observation/nearby-station API, and model-readiness endpoint. Dockerfile, systemd template, deployment notes and automated backend tests exist. The newest backend source is in GitHub; it still must be deployed to the Linux host before the new routes are available there.
- The cyclone overlay now calls GDACS when selected, and a spatial wind overlay has been added to the frontend. These new changes still need a browser end-to-end test after GitHub Pages publishes them.
- Water snapshot now reports source/resource errors, unit counts, state coverage and timestamp quality. Latest successful collector run published 407 records from 37 resources; eight resources had no usable records, with zero source-page/resource errors in that run.
- Historical CWC discharge/rainfall downloader, raw-archive checksum manifest, schema inspection script, station-level quality audit, unverified-coordinate station catalogue, common observation-schema adapter, and a manual GitHub Actions workflow that uploads raw/processed artifacts for seven days. A research-readiness queue now ranks stations for manual review and deliberately blocks coordinate-based weather joins until the coordinate and source URL are independently verified. Exact resource-page and download URLs plus raw-file SHA-256 are now preserved per normalized row and checked by a fail-closed provenance validator; the downloader's CSV filenames are collision-safe across resource URLs. A preliminary audit summary is documented in `docs/cwc-discharge-review.md`.
- Research ML path: a single-gauge PyTorch LSTM for Yadgir, Karnataka, trained successfully and its saved weights passed the inference smoke test in [run #39115932750](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39115932750). On the earlier chronological holdout, RMSE was 1,043.61 m³/s versus 1,274.75 m³/s for persistence, but high-flow NSE was -0.013. This is a real experimental artifact, **not** a validated public flood-warning model. Regional multi-station run #39114366885 was cancelled during training and must be rerun and evaluated.

## Latest risk-map work (added; do not remove existing features)

- Added a dedicated Risk map selector beside the street/terrain/satellite base-map selector: historical NRSC/ISRO flood hazard, GDACS cyclone threat, and combined historic-hazard + cyclone-event view.
- Verified via the NRSC WMS capability catalogue and CI GetMap probes that `ap_hz`, `agg_karnataka`, `agg_kerala`, and `agg_tamilnadu` return PNG images. The map preserves source styling and links to the official hazard atlas. The latest syntax and deployed-site checks passed before the documentation-only updates.
- Remaining: visually inspect tile alignment/legend in a real browser and test a location in each state. Telangana is not verified in the selected WMS catalogue and must remain unknown; do not fill it green. Build and validate a separate live flood-probability model only after suitable rainfall, discharge, catchment and event data are aligned and evaluated. GDACS polygons/markers are source event geometry, not a home-made storm-radius forecast.

## Highest priority: verify the complete experience

1. **Check the live website after GitHub Pages deployment.** Confirm the map, all five-state location search, station table and freshness labels work. Test at least one location in Andhra Pradesh, Telangana, Karnataka, Kerala and Tamil Nadu.
2. **Deploy and check the backend.** The latest repository code adds `/api/v1/river-flow`, `/api/v1/water-observations`, and `/api/v1/models/status`, but GitHub does not automatically update the separately running Linux service. Follow `backend/README.md`, then test `/health`, `/api/v1/status`, `/api/v1/weather`, `/api/v1/river-flow`, `/api/v1/water-observations`, and `/api/v1/models/status` through the HTTPS tunnel. Treat live availability as unresolved until tested from the user's computer.
3. **Check every overlay in a browser.** Test RainViewer freshness/rejection, spatial cloud cover, the new spatial wind arrows/tooltips, and GDACS cyclone events. If a third-party feed blocks browser requests or returns a different schema, keep the overlay error explicit and use official IMD links as the fallback.
4. **Test backend integration.** In the developer tools view, enter the current HTTPS tunnel address (only if the tunnel is running). Check health, status, weather, GloFAS river flow, water records and model readiness. Verify the selected-point map uses the backend when available and clearly falls back to direct providers if a route is missing.
5. **Audit source quality.** For the 407 water records, verify units, station identifiers, timestamps/time zones, coordinates, state labels and freshness. Do not guess locations, rewrite source timestamps without evidence, turn missing values into zero, or equate water level with discharge.
6. **Fix any issues found and retest.** Keep an observed/forecast/modelled label and source timestamp visible. Do not present the current contextual evidence chain as a validated flood warning.
7. **Prepare stable deployment.** A Quick Tunnel hostname is temporary. Before public reliance, deploy behind stable HTTPS, restart the Linux service on server updates, and remove the developer-only connection panel from the final user experience.

## Longer-term engineering work — not yet completed

- Re-run the [historical archive workflow](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/download-historical-hydrology.yml) after the latest review-queue update, inspect the station audit/readiness queue and curate a gauge dataset with documented units and source provenance.
- Re-run the regional multi-station LSTM after fixing workflow cancellation behavior; inspect its actual evaluation artifact and per-lead metrics.
- Validate station-to-catchment and upstream/downstream river connections using reviewed geographic data.
- Extend the successful single-station discharge-only LSTM with verified, time-aligned rainfall/weather inputs, then evaluate high-flow and flood-event performance before considering any warning integration.
- Build a separately validated flood-event or flash-flood model with reviewed positive/negative labels.
- Add inundation extent/depth mapping only when a suitable validated hydrology/hydraulics model and flood footprints are available.
- Add alerts/notifications only after thresholds, reliability, delivery and official-warning handoff are designed and tested.

## Early warning and infrastructure accountability

- The workflow and safeguards are documented in [docs/EARLY_WARNING_AND_ACCOUNTABILITY.md](docs/EARLY_WARNING_AND_ACCOUNTABILITY.md). The dashboard currently explains this plan; it does not yet run a validated alert engine or maintain a server-side evidence register.
- Implemented: the dashboard has a browser-local infrastructure evidence notebook with HTTPS source links, review-status labels, local deletion and JSON export. Remaining: curate reliable public-source links and build a shared/server-side verified register with reviewer identity, correction history and access controls. Missing inspection information must be marked **not verified**. Never infer structural strength from water level or assign blame without a competent investigation.
- Before operational alerts: locally approved thresholds, IMD/CWC/state cross-checking, event-based validation, false-alarm/missed-event analysis, human review, delivery testing and audit logs.

## Source links

- [Website](https://pantheondeified.github.io/FloodWatch-South-India/)
- [Repository](https://github.com/PantheonDeified/FloodWatch-South-India)
- [Water pipeline run report](docs/water-pipeline-run-report.md)
- [Live-data test report](docs/live-data-test-report.md)
- [Model status card](data_pipeline/SUBMISSION_MODEL_CARD.md)
- [Flood Hub gap analysis](FLOOD_HUB_GAP_ANALYSIS.md)

## Safety and operational notes

FloodWatch is an independent research/situational-awareness prototype, not Google Flood Hub and not an official warning system. Never publish a flood probability without validation. Do not commit SSH keys, credentials, or private data. Treat public source timestamps and freshness as source-specific.
