# FloodWatch South India — capabilities and implementation status

**Website:** https://pantheondeified.github.io/FloodWatch-South-India/  
**Repository:** https://github.com/PantheonDeified/FloodWatch-South-India

FloodWatch is a browser-based situational-awareness research prototype for South India. It combines source-labelled public observations, gridded weather estimates, historical rainfall context and external river-flow forecasts in one map-oriented interface. It is inspired by the *problem space* of public flood platforms; it is not a replica of Google's production Flood Hub and is not an official warning service.

## Capability matrix

| Capability | What the user can do | Data/model source | Status and interpretation |
|---|---|---|---|
| Regional interactive map | Explore South India with street, terrain and satellite basemaps; search a place, enter coordinates, click the map or optionally use browser geolocation | Leaflet and public map tiles | Implemented in the website; tile availability and attribution depend on provider |
| Current weather and hourly outlook | Inspect temperature, precipitation, rain/showers, cloud cover and wind at a selected location | Open-Meteo weather model | Live API-dependent; gridded estimates, not a measurement at every location |
| Rain radar | Toggle radar imagery and inspect the displayed source timestamp/freshness | RainViewer | Live overlay; verify the current timestamp and coverage |
| Wind field | Inspect a spatial wind-direction/speed overlay | Open-Meteo | Model-derived wind field, not direct station observations |
| Tropical-cyclone context | View available cyclone/event features and follow official warning links | GDACS; official IMD links | Event context is not a replacement for official IMD advisories |
| Historical rainfall context | Compare recent complete monthly totals and rolling seven-day conditions with ERA5-Land history and a 1991–2020 baseline | ERA5-Land reanalysis | Historical/reanalysis context; not a direct rain-gauge observation |
| River-flow context | Inspect historical and short-range modelled discharge context | Open-Meteo Flood API / GloFAS | External model product; not a local CWC gauge reading and not a FloodWatch-trained forecast |
| Official water-observation explorer | Search/filter source records by state label, measurement type, freshness and name; inspect source links/timestamps; optionally map geolocated stations | Public NWDP/NWIC/CWC-derived snapshot | Implemented; source coverage, coordinate availability, timestamps and update intervals vary. Markers are not alerts |
| Data-quality/provenance pipeline | Download public archive resources, normalize station/time/value fields, retain provenance and report rejected values/resource issues | NWDP/NWIC/CWC public archives | Automated pipeline; quality reports are required to understand coverage and limitations |
| Infrastructure evidence notebook | Manually record public URLs and evidence notes for dam/reservoir inspection/release reports, embankments, drainage, land-use and warning/response timelines; export JSON | User-entered public-document references | Implemented as browser-local demo only; entries are not uploaded, shared, or automatically verified. No dam-strength score or fault attribution is generated. |
| Single-station neural-network experiment | Train an LSTM from historical daily maximum discharge and compare it with a persistence baseline on later years | PyTorch; CWC/NWDP-derived observations | **Trained for one Yadgir, Karnataka station. Research-only; not served by the live site/API** |
| Regional neural-network experiment | Pool eligible station histories and predict a multi-day discharge sequence; evaluate per forecast lead against persistence | Experimental multi-station PyTorch LSTM | Training/evaluation in GitHub Actions; only report regional results after that run finishes and its artifact is inspected |
| API health and data access | Check health/provider status, request weather, river-flow context and paginated water observations; inspect model readiness | FastAPI backend | Backend source is in the repository; GitHub edits do not automatically deploy to the separate Linux host |
| Automated checks | Run data-pipeline unit tests, syntax checks, snapshot validation, regional model smoke tests and Pages builds | GitHub Actions | See the Actions tab and links in the README |

## Neural-network result currently verified

The completed single-station training artifact is available in [GitHub Actions run #39114067094](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114067094), artifact `floodwatch-discharge-lstm-4`. Its JSON report gives the exact split and metrics.

| Chronological holdout metric | LSTM | Persistence |
|---|---:|---:|
| RMSE | 1,043.61 m³/s | 1,274.75 m³/s |
| MAE | 237.77 m³/s | 249.03 m³/s |
| NSE | 0.357 | 0.041 |

Overall RMSE is 18.1% lower than persistence for this one station. However, on the report's high-flow subset, NSE is −0.013; extreme-flow skill remains weak. These figures **must not be represented as regional performance or as validation of flood warnings**.

The regional training workflow uses a 90-day input history and a seven-day forecast horizon. Forecast origins are sampled every seven days to reduce overlapping-window redundancy and memory use. Its separate evaluation artifact is the only valid source for any regional performance claim: [regional training workflow](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/train-regional-lstm.yml).

## What the ML does not do yet

The local experimental LSTMs do not yet use rainfall forecast products, upstream/downstream river-network connectivity, or complete static catchment attributes. They do not estimate flood probability, water depth, inundation extent, household impact or evacuation routes. The trained single-station weights are currently a temporary GitHub Actions artifact, not a model loaded by the production website/API.

No operational warning skill is claimed. Before deployment, the model needs independently evaluated multi-station/multi-event tests, weather-forcing alignment, station-specific and lead-specific metrics, uncertainty estimates, missing-data handling, a durable/versioned artifact and monitored inference. Official IMD, CWC and state disaster-management guidance remains authoritative.

## Useful project links

- [Verified ML metrics and tests](ML_VALIDATION_SNAPSHOT.md)
- [ML upgrade plan](ML_UPGRADE_PLAN.md)
- [Project readiness and acceptance gates](project-readiness.md)
- [Water pipeline report](water-pipeline-report.md)
- [Google Flood Hub gap analysis](../FLOOD_HUB_GAP_ANALYSIS.md)
- [Backend API documentation](../backend/README.md)
