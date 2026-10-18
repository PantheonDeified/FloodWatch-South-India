# Live-data and frontend integration test report

Checked against the repository on 2026-10-18. This is a code/repository inspection plus limited network diagnostics, not a claim that every provider succeeds in a live browser.

## Current feature inventory

| Component | Code status | Verification still required |
|---|---|---|
| Current weather and hourly forecast | Open-Meteo request present; optional FloodWatch backend proxy and direct-provider fallback present | Check at least one location in each of the five core states, confirm source label and units |
| Historical rainfall | ERA5-Land Archive API request and completeness checks present | Test dates/season calculations in all five states and record actual provider response times |
| River discharge | Open-Meteo Flood API request and contextual interpretation present | Confirm returned grid availability and distinguish past model estimates from forecast days |
| Rainfall radar | RainViewer metadata and tile requests present; rejects frame older than 120 minutes | Check API response, radar tile loading, attribution and timestamp in the browser |
| Cloud-cover map overlay | Spatial Open-Meteo grid request is implemented | Test grid rendering after pan/zoom and provider response |
| Wind map overlay | Spatial grid of wind speed/direction has now been added; arrow shows direction toward which wind moves | Browser test needed for provider response shape, arrow orientation, tooltip and mobile layout |
| Cyclone event overlay | Selecting the cyclone layer now invokes the GDACS GeoJSON feed function; popups use text nodes | Browser test needed for CORS, feed schema, event count, alert-level styling and empty/error states |
| Public water snapshot | UI reads data/water-observations.json; collector produced 407 records from 37 resource files | Confirm Pages serves the JSON and table renders records; audit per-record freshness and station location |
| Search/geolocation | Nominatim place search, map click/coordinate entry and optional browser geolocation are in code | Test permissions, outside-coverage behavior and results in all five states |

## What I checked in this run

- Repository source contains the weather proxy, historical rainfall, discharge, RainViewer, cloud, wind, cyclone, and station-snapshot code paths.
- A successful collector run is documented as producing 407 records from 37 resources with the snapshot generated at 2026-10-18T02:32:25Z.
- The public backend had previously passed smoke tests, but the latest check from this execution environment received connection refused from 148.100.98.93:8000. The temporary Cloudflare Quick Tunnel hostname did not resolve from this environment. These results mean the backend needs a fresh check from the user's machine; they do not establish why it is down.
- This execution environment could not resolve the GitHub Pages domain either, so I could not independently confirm the newly published browser page or the large JSON snapshot after the latest commits.
- Code has been updated to connect the wind overlay and cyclone feed handler. Those changes are committed, but not yet proven in a live browser.

## Fast browser smoke test

1. Open https://pantheondeified.github.io/FloodWatch-South-India/ and refresh with Ctrl+F5.
2. Search one town/district in each core state: Andhra Pradesh, Telangana, Karnataka, Kerala and Tamil Nadu.
3. Check current weather, hourly forecast, historical rainfall, river-discharge panel, and note the source timestamp and whether each value is modelled.
4. Click Rain radar, Cloud cover, Wind and Cyclone alerts. Record the exact error/status text if a layer does not load; do not interpret a missing overlay as no hazard.
5. Scroll to the water-observation table and check whether rows appear. Filter by measurement type and search for a station. If markers are enabled, confirm every marker has source-linked coordinates and a sensible measurement type.
6. On the user's computer, test the current backend URL's /health, /api/v1/status and /api/v1/weather?latitude=19.15&longitude=77.30 endpoints. A Cloudflare Quick Tunnel only works while that tunnel is running; use the currently displayed URL, never a stale hostname.

## Interpretation guardrails

- Open-Meteo forecast/reanalysis and GloFAS values are model outputs, not station measurements.
- RainViewer radar coverage and age vary.
- NWDP/NWIC rows are source-reported measurements but their latest timestamps vary by resource; collector retrieval time is not the observation time.
- GDACS events supplement but do not replace official IMD warnings.
- FloodWatch is a prototype, not an official warning system or a validated local flood-probability service.
