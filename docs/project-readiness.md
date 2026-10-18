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

## Acceptance criteria for 100%

| Workstream | 100% completion gate |
|---|---|
| Frontend map and interaction | Automated desktop/mobile browser tests cover navigation, location selection, map layers, loading/error states, accessibility and failure recovery |
| Backend APIs | All routes, validation, timeouts and provider failures tested; latest code deployed on stable HTTPS with monitoring and load/security checks |
| Live data integration | Every source has verified attribution, units, timestamps, freshness, coverage, error handling and tested refresh behavior |
| Historical data pipeline | Station identity, coordinates, units, continuity and provenance are reviewed; discharge and weather are aligned; basin mapping and repeatable data-quality reports are independently checked |
| ML / neural networks | Reproducible model beats baseline on independent chronological/event holdouts across representative stations and high flows; uncertainty/missing data are handled; report passes review before shadow deployment |
| Production readiness | Stable deployment, logging/monitoring, security/privacy, rollback, uptime checks and an end-to-end human-reviewed alert drill are demonstrated |

## Runbooks

- [Refresh official water observations](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/refresh-water-observations.yml)
- [Download historical hydrology](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/download-historical-hydrology.yml)
- [Run the LSTM pilot](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/run-streamflow-lstm-pilot.yml)
- [Backend tests](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/backend-tests.yml)
- [Production smoke checks](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/production-smoke-check.yml)

## Non-negotiable model safety gate

External Open-Meteo Flood API / GloFAS outputs are external model estimates, not FloodWatch-trained predictions. Do not label the project as having a validated local flood model until verified gauge data is available, the trained model beats the persistence baseline on held-out time periods, the review gate passes, and a human review approves shadow deployment. Never treat missing records as flood-free labels or convert water level to discharge without a verified rating curve/source conversion.
