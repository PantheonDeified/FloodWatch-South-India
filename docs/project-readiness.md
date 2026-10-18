# FloodWatch South India — completion gates

This checklist is an engineering status document, not a claim that flood forecasting is operationally validated. A category reaches 100% only when its acceptance tests and evidence exist.

## Six workstreams

| Workstream | What counts as 100% | Evidence currently available | Remaining blocker |
|---|---|---|---|
| Frontend map and interaction | Map loads; location search, map clicks, supported layers and empty/error states work across desktop/mobile browsers; automated browser checks pass | GitHub Pages deployment; frontend JavaScript syntax workflow; location-driven map and data panels | Full browser/device interaction testing and accessibility review |
| Backend APIs | All documented routes validated, request limits and errors tested, service deployment stable under HTTPS with monitoring | FastAPI health/status/weather/river-flow/water-observation/model-status routes; backend CI tests and container build | Stable managed HTTPS hosting, uptime checks, rate/timeout/load tests |
| Live data integration | Each provider has source attribution, units, timestamps, freshness handling, failure behavior and tested refresh cadence | Open-Meteo weather/flood-model integration; RainViewer/GDACS overlays; scheduled NWDP/NWIC snapshot collector and schema validation | Verify every live feed in deployed browser; improve station coordinate/timezone coverage; distinguish source updates from observation freshness |
| Historical data pipeline | Source-reviewed observed discharge + weather are normalized, provenance/unit checks pass, basin mapping is reviewed and repeatable artifacts are produced | NWDP/CWC downloader, archive inspector, normalization and weather/feature scripts, basin assignment, readiness audit | Download and inspect archive; validate station IDs, units, continuity and timezone semantics; build verified daily feature CSV |
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
