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
- GitHub Pages project and a FastAPI backend on IBM LinuxONE. The health and status endpoints returned JSON through the temporary HTTPS tunnel. The versioned `backend/main.py` now includes a South-India-bounded Open-Meteo weather proxy; it still needs to be deployed to the running Linux server and tested.

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

## Person 2 — Fix and verify river/water observations

**Goal:** Make the existing water-observation data file contain real, validated records if public sources allow it.

1. Inspect `data_pipeline/scripts/refresh_water_observations.py`, the GitHub Actions workflow, and `data/water-observations.json`.
2. Find why the committed water-observation JSON is empty and run or repair the collector.
3. Verify source links and record fields such as station/location, value, units, observation time, retrieval time, and source.
4. Add validation for missing/invalid values and stale readings.
5. Run the GitHub Actions workflow and document the result. If a source cannot be accessed, report that honestly; never create fake readings.

**Deliver:** a valid `data/water-observations.json` if real records can be obtained, tests where feasible, and `docs/water-pipeline-report.md`.

**Simple AI prompt:**  
“Inspect the existing FloodWatch South India water-observation collector, workflow, and JSON schema. Diagnose why data/water-observations.json is empty. Make the smallest safe fix, use only real public-source records, preserve the current schema, validate timestamps/units/values, and add tests. Do not fabricate readings or edit index.html. Report changed files and how to test them.”

## Project lead — Frontend, map, and backend

1. Deploy `backend/main.py` to the IBM LinuxONE server by following `backend/README.md`; preserve the existing `main.py` backup and run `python -m py_compile` before restarting.
2. Test `GET /api/v1/weather?latitude=19.15&longitude=77.30` locally and through the HTTPS tunnel; confirm the JSON contains `current`, `hourly`, and `_floodwatch` metadata.
3. Open the published website and verify the backend panel appears after GitHub Pages redeploys. Paste the current HTTPS tunnel URL, test `/health` and `/api/v1/status`, then select a map point and confirm the status says `FloodWatch API → Open-Meteo` (rather than direct fallback).
4. Keep the Linux API and Quick Tunnel running during the demo; the temporary URL is not a permanent deployment.
5. Integrate teammates’ verified outputs only after reviewing their pull requests; then check timestamps and locations across all five states.

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
- The water-data pipeline is either producing verified records or has a documented blocker and next step.
- The published map and existing layers have been tested.
- The backend's HTTPS integration status is stated accurately.
- The demo clearly distinguishes measurements, forecasts, and model estimates.

**Prototype limitation:** FloodWatch is a monitoring and situational-awareness prototype, not a validated flood-prediction or official-warning system.
