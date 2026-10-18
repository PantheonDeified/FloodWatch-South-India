# FloodWatch South India — Remaining Tasks for the Team

This is a short task list for tonight. You can do the work yourself or paste your task into an AI coding assistant. Do not invent data, and do not overwrite other people's work.

## What is already built

- Interactive Leaflet map for South India with street, terrain, and satellite map layers.
- Place search, map-click selection, coordinate entry, and optional browser location.
- Open-Meteo weather and hourly forecast.
- RainViewer radar layer.
- Historical rainfall comparisons using ERA5-Land.
- Modelled river-discharge context using Open-Meteo Flood API/GloFAS.
- Water-observation table interface, filters, and a rainfall-to-river evidence chain.
- GitHub Pages project and a FastAPI backend on IBM LinuxONE. Version 0.2.0 is running; `/health`, `/api/v1/status`, and `/api/v1/weather` returned responses, and the HTTPS developer checker confirmed the weather proxy is available. Automated backend tests and the syntax check now pass in GitHub Actions. The tunnel URL remains temporary.

These features still need end-to-end testing. A feature in the code does not automatically mean every live data source is currently working.

## Person 1 — Test weather and rainfall data

**Goal:** Find out which existing weather layers actually work.

1. Test the weather, hourly forecast, radar, historical rainfall, and river-discharge requests already used by the site.
2. Test at least one location in each of Karnataka, Kerala, Tamil Nadu, Telangana, and Andhra Pradesh.
3. Record whether each request works, the source, units, timestamps, and whether the data is observed, forecast, or modelled.
4. Report broken or stale sources and suggest fixes. Do not redesign the map or edit `index.html` without asking the project lead.

**Deliver:** `docs/live-data-test-report.md` and, if useful, `docs/weather-api-examples.md`.

**Simple AI prompt:**  
“Review the existing FloodWatch South India repository. Identify the weather, rainfall, radar, historical rainfall, and river-discharge data requests already present. Test or inspect them without inventing results. Create a report with source URLs, units, timestamps/freshness, whether each is observed/forecast/modelled, five-state test coverage, errors, and practical fixes. Do not change index.html.”

## Person 2 — Validate and improve water-observation quality

**Goal:** Make the existing source-linked water data safer and easier to interpret. A successful collector run produced 407 records from 37 resource files; the problem is now coverage, freshness, metadata and repeatable validation rather than a completely empty dataset.

1. Read `docs/water-pipeline-run-report.md` and inspect the latest `data/water-observations.json` snapshot.
2. Audit missing station coordinates, missing state/district fields, source timestamps, units and rows with suspicious jumps or implausible values. Do not guess coordinates or silently delete source values; record each issue and its rationale.
3. Confirm source timezone semantics for each dataset, or leave them explicitly unspecified. Distinguish hourly telemetry from manual/daily observations.
4. Test the collector and GitHub Actions workflow after the new non-empty-snapshot guard. Verify the workflow does not trigger itself solely from its generated output file.
5. Document source/resource errors, coverage gaps, and safe fixes. Never fabricate readings.

**Deliver:** `docs/water-pipeline-report.md` with a repeatable quality audit and tests/checks where feasible. Use `docs/water-pipeline-run-report.md` as the first run summary.

**Simple AI prompt:**  
“Review the existing FloodWatch South India water snapshot (407 records generated from 37 resources), collector and report. Audit source timestamps/timezones, units, missing coordinates/state fields, out-of-core-area records, and suspicious values. Do not fabricate or silently alter source readings. Add safe validation/tests for issues that can be reliably checked, preserve source provenance, and document unresolved issues in docs/water-pipeline-report.md. Do not edit index.html.”

## Project lead — Frontend, map, and backend

1. Open the [developer tools view](https://pantheondeified.github.io/FloodWatch-South-India/?devtools=1), paste the current HTTPS tunnel URL into the hidden-by-default panel, and confirm `/health`, `/api/v1/status`, and `/api/v1/weather` all report success; the checker has already reported `weather_proxy.available: true`.
2. Select map points in all five states and confirm the weather status says `FloodWatch API → Open-Meteo`, not the direct-provider fallback. Test browser console errors, the hourly panel, and the location search/geolocation controls.
3. Review `docs/water-pipeline-run-report.md` and verify the station table loads the 407-record published snapshot. Check map locations and freshness labels; do not describe the snapshot as uniformly real-time.
4. Keep the Linux API and Quick Tunnel running during the demo; the temporary URL is not a permanent deployment.
5. Integrate teammates’ verified outputs only after reviewing their pull requests; then prepare a demo that distinguishes measured/public source observations, model estimates and forecasts.

**Important:** Do not hardcode a temporary Cloudflare URL as a permanent endpoint. A Quick Tunnel URL only works while the tunnel is running and is not a reliable production deployment.

**Before final public release:** remove the developer-only backend testing panel from `index.html`, deploy the API to a stable HTTPS address, configure the frontend to use that stable address, and verify that no temporary tunnel URL is embedded in the public code.

## GitHub handoff

Each teammate should:

1. Pull the latest `main`.
2. Work on a separate branch:
   - Person 1: `feature/live-data-validation`
   - Person 2: `fix/water-observation-pipeline`
3. Commit only their own changes and push the branch.
4. Open a pull request into `main`.
5. The project lead reviews and tests before merging.

Do not let both teammates edit `index.html`. Never commit SSH keys, API secrets, or private/patient data.

## Tonight's definition of done

- Weather/rainfall data has a clear source, units, and freshness report.
- The water-data pipeline produces source-linked records; timestamp timezone, freshness and station-coverage limitations are documented and tested.
- The published map and existing layers have been tested.
- The backend's HTTPS integration status is stated accurately.
- The demo clearly distinguishes measurements, forecasts, and model estimates.

**Prototype limitation:** FloodWatch is a monitoring and situational-awareness prototype, not a validated flood-prediction or official-warning system.
