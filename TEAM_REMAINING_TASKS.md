# FloodWatch South India — Single-Owner Remaining Tasks

The project lead is handling the tasks that were originally split between teammates. Use this file as the integrated checklist; do not wait for separate teammate reports.

## Implemented in the repository

- Interactive Leaflet map with street, terrain and satellite basemaps.
- Place search, map-click selection, coordinate entry, and optional browser geolocation.
- Open-Meteo current conditions and hourly forecast; ERA5-Land historical rainfall comparisons; Open-Meteo Flood API/GloFAS modelled river-discharge context.
- RainViewer radar and Open-Meteo spatial cloud-cover overlay.
- Public NWDP/NWIC observation collector, source registry, six-hour GitHub Actions workflow, snapshot validator, tests, and frontend table/map reader.
- Successful water collector run produced 407 records from 37 resource files across 20 configured source pages. This is not proof every source is fresh or complete.
- FastAPI backend source, health/status/weather routes, deployment notes, and an automated backend test workflow.
- The cyclone overlay now calls GDACS when selected, and a spatial wind overlay has been added to the frontend. These new changes still need a browser end-to-end test after GitHub Pages publishes them.
- Documentation now states that the water snapshot contains records rather than incorrectly describing it as empty.

## Highest priority: verify the complete experience

1. **Check the live website after GitHub Pages deployment.** Confirm the map, all five-state location search, station table and freshness labels work. Test at least one location in Andhra Pradesh, Telangana, Karnataka, Kerala and Tamil Nadu.
2. **Check the backend.** Test /health, /api/v1/status, and /api/v1/weather?latitude=19.15&longitude=77.30. The API previously worked, but the latest check from the current execution environment got connection refused on 148.100.98.93:8000; the temporary Quick Tunnel could not be resolved from that environment. Treat backend availability as unresolved until tested from the user's computer.
3. **Check every overlay in a browser.** Test RainViewer freshness/rejection, spatial cloud cover, the new spatial wind arrows/tooltips, and GDACS cyclone events. If a third-party feed blocks browser requests or returns a different schema, keep the overlay error explicit and use official IMD links as the fallback.
4. **Test backend integration.** In the developer tools view, enter the current HTTPS tunnel address (only if the tunnel is running). Check health, status and weather. On the selected map points, verify the weather source says FloodWatch API → Open-Meteo rather than direct fallback.
5. **Audit source quality.** For the 407 water records, verify units, station identifiers, timestamps/time zones, coordinates, state labels and freshness. Do not guess locations, rewrite source timestamps without evidence, turn missing values into zero, or equate water level with discharge.
6. **Fix any issues found and retest.** Keep an observed/forecast/modelled label and source timestamp visible. Do not present the current contextual evidence chain as a validated flood warning.
7. **Prepare stable deployment.** A Quick Tunnel hostname is temporary. Before public reliance, deploy behind stable HTTPS, restart the Linux service on server updates, and remove the developer-only connection panel from the final user experience.

## Longer-term engineering work — not yet completed

- Build a curated historical gauge dataset with documented units and source provenance.
- Validate station-to-catchment and upstream/downstream river connections using reviewed geographic data.
- Establish baseline streamflow forecasts and only then train/evaluate an LSTM or other local model on suitable discharge data and aligned weather inputs.
- Build a separately validated flood-event or flash-flood model with reviewed positive/negative labels.
- Add inundation extent/depth mapping only when a suitable validated hydrology/hydraulics model and flood footprints are available.
- Add alerts/notifications only after thresholds, reliability, delivery and official-warning handoff are designed and tested.

## Source links

- [Website](https://pantheondeified.github.io/FloodWatch-South-India/)
- [Repository](https://github.com/PantheonDeified/FloodWatch-South-India)
- [Water pipeline run report](docs/water-pipeline-run-report.md)
- [Live-data test report](docs/live-data-test-report.md)
- [Model status card](data_pipeline/SUBMISSION_MODEL_CARD.md)
- [Flood Hub gap analysis](FLOOD_HUB_GAP_ANALYSIS.md)

## Safety and operational notes

FloodWatch is an independent research/situational-awareness prototype, not Google Flood Hub and not an official warning system. Never publish a flood probability without validation. Do not commit SSH keys, credentials, or private data. Treat public source timestamps and freshness as source-specific.
