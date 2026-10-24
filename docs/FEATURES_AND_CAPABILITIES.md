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
| NASA satellite precipitation imagery | Toggle an optional NASA GPM IMERG precipitation-rate visualization on the map and open NASA Earthdata resources | NASA GIBS / GPM IMERG reference services | Visualization only; it is not treated as a direct gauge and is not yet an input to the numerical risk score. Availability/product latency depend on NASA's service. |
| Tropical-cyclone context | View available cyclone/event features and follow official warning links | GDACS; official IMD links | Event context is not a replacement for official IMD advisories |
| Historical rainfall context | Compare recent complete monthly totals and rolling seven-day conditions with ERA5-Land history and a 1991–2020 baseline | ERA5-Land reanalysis | Historical/reanalysis context; not a direct rain-gauge observation |
| River-flow context | Inspect historical and short-range modelled discharge context | Open-Meteo Flood API / GloFAS | External model product; not a local CWC gauge reading and not a FloodWatch-trained forecast |
| Official water-observation explorer | Search/filter source records by state label, measurement type, freshness and name; inspect source links/timestamps; optionally map geolocated stations | Public NWDP/NWIC/CWC-derived snapshot | Implemented; source coverage, coordinate availability, timestamps and update intervals vary. Markers are not alerts |
| FloodWatch continuous risk contours | The map shows a smooth interpolated colour field with connected score-35 and score-65 contour curves instead of square risk cells. Map clicks inspect the nearest calculated sample and its components. | Open-Meteo forecast fields, GloFAS modelled discharge, fresh gauge histories, local evidence, and regional-LSTM station discharge ranks | Implemented in the local project copy; thresholds remain experimental and uncalibrated. LSTM station ranks modify scores by at most 25% only when HydroBASINS shows the same sub-basin or a `NEXT_DOWN` chain to the selected basin (up to six links); unmatched basins receive no LSTM input. Source-linked incidents remain gated by coordinates, recency, review and hydrologic link. Contours are a visual aid, not a calibrated probability; transparent = unknown. |
| Forecast freshness and coverage | See the weather model timestamp, rainfall and probability hour coverage, and whether river/reservoir inputs are available at the selected point | Open-Meteo and GloFAS responses | Displayed per selected point; the point score requires all 24 next-hour precipitation values. Missing rainfall values are not silently treated as zero. |
| Saved places and opt-in alerts | Keep up to ten places in this browser, choose an elevated/high score threshold, receive notifications on a new threshold crossing, and export score history | Browser local storage, Open-Meteo/GloFAS, browser Notifications API | Checks about every 15 minutes while the page is open; requires notification permission. Score archive and alert state stay on the device; no background checking while closed and no official warning delivery. |
| Map-score event verification | Join exported score history with independently reviewed flood event/no-event labels; report out-of-time discrimination, calibration, false alarms, recall and reliability | `evaluate_map_score_events.py` and verification CSV template | Implemented pipeline; no reviewed event archive is bundled, so measured event accuracy is unavailable until labels are curated. Unknown/reporting-gap dates must not be labelled as non-events. |
| Historical flood evidence + cyclone risk map | Separate selector alongside street/terrain/satellite basemaps; displays Andhra Pradesh flood-hazard zonation (`ap_hz`) plus aggregated historic flood-map layers for Karnataka/Kerala/Tamil Nadu (`agg_karnataka`, `agg_kerala`, `agg_tamilnadu`), and current/recent GDACS cyclone event geometry; existing rain/cloud/wind overlays remain independent | NRSC Bhuvan WMS; GDACS event GeoJSON | WMS GetMap and Leaflet EPSG:3857 probes returned PNGs for all four configured layers in CI. NRSC describes the Andhra hazard atlas as inundation-frequency mapping for 1998–2019 and the state aggregates as historic satellite-derived flood maps from 2003–2020; these products are not equivalent calibrated risk scores. MapCache GetLegendGraphic returns HTTP 501, so UI links to official atlas rather than inventing thresholds. Telangana remains unknown/unclassified, not green/safe. Cyclone events are source alerts, not predicted storm-impact radii. |
| Data-quality/provenance pipeline | Download public archive resources, normalize station/time/value fields, retain provenance and report rejected values/resource issues | NWDP/NWIC/CWC public archives | Automated pipeline; quality reports are required to understand coverage and limitations |
| Infrastructure evidence notebook and risk contributions | Enter public-source evidence for dated dam/gate abnormal operations, embankment breach/erosion, blocked drainage and floodplain/land-use changes; attach location coordinates and a hydrologic-link checkbox; export JSON | User-entered HTTPS public-document references | Browser-local demo. Only accepted/reviewed, current, geolocated categories can influence the experimental risk score; dam/gate reports need a verified hydrologic link. Inspections or response timelines alone do not imply danger or automatic blame. No dam-strength score is inferred. |
| Single-station neural-network experiment | Train an LSTM from historical daily maximum discharge and compare it with a persistence baseline on later years | PyTorch; CWC/NWDP-derived observations | **Trained for one Yadgir, Karnataka station. Research-only; not served by the live site/API** |
| Regional neural-network experiment | Pool eligible station histories and predict a seven-day discharge sequence; evaluate pooled, per-station and high-flow outcomes against persistence | Experimental multi-station PyTorch LSTM | Trained forecasts are published in a scheduled snapshot and can modify experimental map scores through the HydroBASINS connectivity gate; optional backend inference is available when assets exist. Published performance is mixed across stations, and the model is not validated for public warnings. |
| Rainfall-forced discharge experiment | Train a single-station LSTM with historical weather/discharge and supply a daily rainfall forecast at inference | New PyTorch research scripts | Available as a reproducible experiment, not deployed. Historical evaluation uses reanalysis rain observed after the forecast origin as perfect future forcing; results are optimistic and not forecast-skill evidence. |
| API health and data access | Check health/provider status, request weather, river-flow context and paginated water observations; inspect model readiness | FastAPI backend | Backend source is in the repository; GitHub edits do not automatically deploy to the separate Linux host |
| Automated checks | Run data-pipeline unit tests, syntax checks, snapshot validation, regional model smoke tests and Pages builds | GitHub Actions | See the Actions tab and links in the README |

## Continuous risk-contour interpretation

FloodWatch sets colour from its own raw numerical inputs, not other websites' risk colours. Rainfall components use project-defined relative scaling (100 mm over 24h, 150 mm over 72h, 20 mm/h current precipitation saturate their components); weights are 40/30/15/15. Where GloFAS data exist, the next-seven-day discharge peak is ranked against up to 92 previous days at the same coordinate. Recent gauge histories with at least 10 usable points can add station-relative high-level, rise and rapid-rise signals; only fresh source times are eligible for these live signals. Eligible regional-LSTM station ranks can also affect scores only through the mapped same-basin/upstream `NEXT_DOWN` gate. Geolocated, current, source-linked human-made incident entries can contribute under strict review and hydrologic-link rules. The risk renderer now uses an interpolated continuous surface and connected 35/65 threshold contour polylines. Colours and contour lines remain **experimental and uncalibrated against labelled flood events**; do not describe them as probabilities, dam-safety ratings or official warnings. Cells without mapped basin linkage receive no LSTM adjustment; missing numeric coverage stays transparent/unknown, never green.

## Neural-network result currently verified

The completed single-station training artifact is available in [GitHub Actions run #39114067094](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39114067094), artifact `floodwatch-discharge-lstm-4`. Its JSON report gives the exact split and metrics.

| Chronological holdout metric | LSTM | Persistence |
|---|---:|---:|
| RMSE | 1,043.61 m³/s | 1,274.75 m³/s |
| MAE | 237.77 m³/s | 249.03 m³/s |
| NSE | 0.357 | 0.041 |

Overall RMSE is 18.1% lower than persistence for this one station. However, on the report's high-flow subset, NSE is −0.013; extreme-flow skill remains weak. These figures **must not be represented as regional performance or as validation of flood warnings**.

The regional training workflow uses a 90-day input history and a seven-day forecast horizon. The accelerated run samples forecast origins every 14 days to reduce repeated overlapping windows and memory use. The [regional training artifact](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39122959850) reports RMSE skill versus persistence of 46.1% pooled, but only 107/223 station holdouts and 63/119 comparable high-flow station subsets beat persistence on RMSE. A scheduled forecast snapshot can feed the browser's experimental basin-gated score contribution; the model is not validated for public warnings.

## What the ML does not do yet

The deployed regional LSTM does not use rainfall forecast products or static catchment attributes; its map contribution is spatially gated by HydroBASINS basin polygons and `NEXT_DOWN` links, which are approximate basin relationships rather than surveyed river routing. A separate single-station rainfall-forced experiment consumes future rain at inference, but its training backtest uses observed-after-origin reanalysis rain and its weights are not deployed. The local score separately considers fresh nearby gauge rise/high-level indicators; proximity alone does not establish hydrologic connectivity. The map's user-entered human-made incident evidence is source-gated and does not infer dam strength or operator fault. The models do not estimate flood probability, water depth, inundation extent, household impact or evacuation routes.

No operational warning skill is claimed. Before deployment, the model needs independently evaluated multi-station/multi-event tests, weather-forcing alignment, station-specific and lead-specific metrics, uncertainty estimates, missing-data handling, a durable/versioned artifact and monitored inference. Official IMD, CWC and state disaster-management guidance remains authoritative.

## Useful project links

- [Verified ML metrics and tests](ML_VALIDATION_SNAPSHOT.md)
- [ML upgrade plan](ML_UPGRADE_PLAN.md)
- [Project readiness and acceptance gates](project-readiness.md)
- [Water pipeline report](water-pipeline-report.md)
- [Google Flood Hub gap analysis](../FLOOD_HUB_GAP_ANALYSIS.md)
- [Backend API documentation](../backend/README.md)
