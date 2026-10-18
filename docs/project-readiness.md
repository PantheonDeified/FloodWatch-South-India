# FloodWatch South India — completion gates

This checklist is an engineering status document, not a claim that flood forecasting is operationally validated. A category reaches 100% only when its acceptance tests and evidence exist.

## Current completion snapshot — 18 October 2026

Percentages below are **engineering estimates against the full acceptance criteria**, not model-accuracy percentages. A feature can be implemented while its operational reliability or scientific validation remains incomplete.

| Workstream | Estimated completion | Verified evidence | Remaining work before 100% |
|---|---:|---|---|
| Frontend map and interaction | 80% | GitHub Pages build/deploy succeeds; map/place search/coordinates and available weather/radar/wind/river/water layers exist; problem-solving, early-awareness and infrastructure-accountability section added to the dashboard | Automated browser/device tests, accessibility review, verify each overlay live and test degraded-network behavior |
| Backend APIs | 70% | FastAPI route tests pass in [run #39115737274](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39115737274); container build and Python compilation pass; model-status endpoint now states that trained weights are not served | Deploy latest backend code to the separate host; stable HTTPS/uptime monitoring, rate/load/timeout testing and prediction-serving integration |
| Live data integration | 70% | Scheduled NWDP/NWIC snapshot collector and schema validation; prior snapshot reported 407 records across 37 resource files; weather/radar/wind/cyclone/river-flow context and official-source links in site | Improve station coordinates/timezone coverage, validate live feeds in deployed browser, monitor source timestamps and document provider outages/freshness |
| Historical data pipeline | 65% | Archive download and normalization steps have succeeded in current training workflows; quality report generated; unit tests and snapshot audit pass in [run #39115535012](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39115535012) | Review station IDs, units, continuity and coordinates; inspect current training outputs; build aligned rainfall/discharge features and reviewed basin mappings |
| ML / neural networks | 35% | One Yadgir, Karnataka single-station discharge LSTM trained and was evaluated chronologically against persistence in [run #39114067094](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114067094); regional-LSTM smoke tests pass in [run #39115379279](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39115379279); regional training and a fresh single-station train-plus-inference-check were launched separately | Inspect the **current** single-station and regional final reports; high-flow skill is weak in the earlier single-station report; add aligned forecast rainfall/catchment features, multi-event validation, uncertainty, and only later shadow deployment |
| Production readiness | 45% | Pages deployment and automated backend/data/ML checks; documented model card, feature matrix, readiness gates and limitations | Latest browser smoke checks; deploy latest backend; logging/alerting, secrets/security review, privacy, rollback plan, monitoring and end-to-end alert drill |

**Approximate aggregate across these six workstreams: 61%** (simple unweighted average of the estimates above). It is a planning indicator, not a certification or performance score.

## Six workstreams

| Workstream | What counts as 100% | Evidence currently available | Remaining blocker |
|---|---|---|---|
| Frontend map and interaction | Map loads; location search, map clicks, supported layers and empty/error states work across desktop/mobile browsers; automated browser checks pass | GitHub Pages deployment; frontend JavaScript syntax workflow; location-driven map and data panels | Full browser/device interaction testing and accessibility review |
| Backend APIs | All documented routes validated, request limits and errors tested, service deployment stable under HTTPS with monitoring | FastAPI health/status/weather/river-flow/water-observation/model-status routes; backend CI tests and container build | Stable managed HTTPS hosting, uptime checks, rate/timeout/load tests |
| Live data integration | Each provider has source attribution, units, timestamps, freshness handling, failure behavior and tested refresh cadence | Open-Meteo weather/flood-model integration; RainViewer/GDACS overlays; scheduled NWDP/NWIC snapshot collector and schema validation | Verify every live feed in deployed browser; improve station coordinate/timezone coverage; distinguish source updates from observation freshness |
| Historical data pipeline | Source-reviewed observed discharge + weather are normalized, provenance/unit checks pass, basin mapping is reviewed and repeatable artifacts are produced | NWDP/CWC downloader and archive inspector; discharge normalization, per-station audit, coordinate-unverified station catalogue, schema adapter, station review queue, and test coverage | Re-run the archive workflow after the new queue step, review the per-station reports, validate station IDs/units/continuity/timezone semantics, independently verify station coordinates and build a verified daily feature CSV |
| ML / neural networks | A model trains reproducibly on verified South Indian gauge data, beats persistence on a chronological holdout, passes review gate, and is monitored in a shadow deployment | PyTorch LSTM trainer, scikit-learn event-classifier code, chronological metrics, persistence baseline and readiness gate | No verified feature table or trained/validated artifact yet; event labels need documented sources; model must pass independent review |
| Production readiness | Stable HTTPS backend, repeatable CI, deployment smoke checks, logging/alerts, documented limitations, security/privacy and load tests, rollback plan | GitHub Pages deployment, backend/container CI, scheduled site/snapshot smoke-check workflow, API docs and source limitations | Smoke-check run evidence; stable backend hosting; operational monitoring, rate limiting and security/load review |

## Runbooks

- [Refresh official water observations](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/refresh-water-observations.yml)
- [Download historical hydrology](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/download-historical-hydrology.yml)
- [Run the LSTM pilot](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/run-streamflow-lstm-pilot.yml)
- [Backend tests](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/backend-tests.yml)
- [Production smoke checks](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/production-smoke-check.yml)

## Non-negotiable model safety gate

External Open-Meteo Flood API / GloFAS outputs are external model estimates, not FloodWatch-trained predictions. Do not label the project as having a validated local flood model until verified gauge data is available, the trained model beats the persistence baseline on held-out time periods, the review gate passes, and a human review approves shadow deployment. Never treat missing records as flood-free labels or convert water level to discharge without a verified rating curve/source conversion.
