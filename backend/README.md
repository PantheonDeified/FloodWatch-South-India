# FloodWatch API backend

This folder contains the versioned FastAPI service source.

## Endpoint summary

- `GET /` — basic service information.
- `GET /health` — health check.
- `GET /api/v1/status` — provider and capability status.
- `GET /api/v1/river-flow?latitude=19.15&longitude=77.30` — 90-day historical context and 7-day Open-Meteo Flood API/GloFAS discharge series; this is modelled external data, not a locally trained FloodWatch prediction.
- `GET /api/v1/water-observations?state=Kerala&limit=100` — paginated published NWDP/NWIC snapshot with optional state, measurement kind, freshness, search, and nearby-coordinate/radius filters. Nearby results use only published station coordinates and include `distance_km`; records without usable coordinates are excluded. If the repo data file is absent on the server, it fetches the public snapshot from GitHub and caches it for five minutes.
- `GET /api/v1/models/status` — evaluation metrics plus a file-based readiness check for the local ML virtual environment, normalized observations, model weights, scalers and report.
- `GET /api/v1/models/regional-discharge/forecast` — runs saved-weight regional LSTM inference when local assets exist. It accepts an exact `station_id`, or `all_stations=true` to return forecasts, coordinates and station-relative historical peak-discharge ranks for eligible stations. Results are cached for 10 minutes; missing runtime/model assets return HTTP 503.
- `GET /api/v1/weather?latitude=19.15&longitude=77.30` — current Open-Meteo model conditions and two days of hourly forecast for coordinates within the prototype's South India coverage (latitude 7–21.8, longitude 73–87).

The water endpoint returns source-reported measurements and labels freshness unknown if a naive timestamp has no reliable timezone. A snapshot's generation time is not the same as the time of every measurement.

The weather response preserves Open-Meteo's normal response fields (`current`, `hourly`, `timezone`) and adds a `_floodwatch` metadata object. The values are gridded model estimates and forecasts, not direct measurements from a local station. This API does not issue a flood probability or official warning.

## DEM hydrology and Leaflet terrain layer

The experimental DEM pipeline is implemented in `backend/dem_hydrology_engine.py` and `backend/export_hazard_geojson.py`. It requires a **real georeferenced elevation raster** (GeoTIFF with a coordinate reference system); there is deliberately no random/synthetic DEM fallback.

From the repository root, install runtime dependencies and run:

```bash
python -m pip install -r backend/requirements.txt
python backend/export_hazard_geojson.py --dem /path/to/your/real_dem.tif
```

By default, the pipeline reprojects a DEM tile to a local UTM coordinate system at 30 m, conditions enclosed depressions with a priority-flood algorithm, calculates slope, D8 flow direction/accumulation, specific catchment area and `TWI = ln(SCA / tan(slope))`, then scales a local TWI percentile stretch by a 24-hour rainfall estimate. If `--rainfall-24h-mm` is omitted, it queries Open-Meteo at the DEM tile centre and refuses to publish a new index if the recent hourly series is unavailable or too incomplete.

Optional arguments:

```bash
python backend/export_hazard_geojson.py \
  --dem /path/to/your/real_dem.tif \
  --output data/dem-inundation-zones.geojson \
  --rainfall-24h-mm 85 \
  --cell-size-meters 30 \
  --min-index 0.25 \
  --max-features 25000
```

`--rainfall-24h-mm` is an explicit override and should be labelled with its true source/time when used. The default limit is one million projected cells because priority-flood/D8 conditioning uses per-cell graph traversal; clip very large DEMs to a relevant basin, and inspect nodata edges/outlets. The pipeline writes diagnostic rasters under `backend/output/dem/`: conditioned DEM, slope (radians), flow accumulation (cells), approximate specific catchment area, TWI and the final screening index. GeoJSON output is capped for browser performance and contains `hazard_index`, TWI, slope, flow-accumulation and rainfall metadata.

### Display it in Leaflet

After running the pipeline, publish `data/dem-inundation-zones.geojson` on the same GitHub Pages branch. Then choose **DEM terrain/wetness index** in the map-layer selector. The UI fetches `data/dem-inundation-zones.geojson`, colors each polygon by `hazard_index` via Leaflet `fillColor`, and provides popups with the index and terrain measurements. When the generated file is absent or empty, the layer displays an explicit unavailable/empty message and does not paint invented coverage. **No DEM raster was supplied with this repository update**, so the GeoJSON is not generated automatically and the map will remain unavailable until you run the command with a real DEM.

### Scientific and operational limits

- The map is a **terrain/rainfall screening index**, not a calibrated flood/inundation probability or official alert. The TWI percentile normalization is relative to the input tile; scores can change with DEM extent and resolution.
- Rainfall is one estimate applied uniformly across the DEM tile. The prototype does not simulate river-channel hydraulics, flood depth, bridge/culvert capacity, drainage networks, structure failures or hydrologic boundary conditions.
- Priority-flood/D8 flow routing and the specific-catchment-area conversion are raster approximations. Flats, nodata boundaries and tile edges can change results; compare with a trusted hydrology package, reference catchments and known flood extents before research or operational use.
- The default 150 mm rainfall scaling is a project heuristic, not an IMD-verified probability threshold. Never use green or blank cells as assurance of safety. Follow official IMD/CWC/NDMA warnings.


## Build a container image

From the repository root:

```bash
docker build -f backend/Dockerfile -t floodwatch-api:0.6.0 .
docker run --rm -p 8000:8000 floodwatch-api:0.6.0
```

The container runs as a non-root user and includes a health check. It fetches the published water snapshot from the repository because the image intentionally contains only the API source, not the full data directory. For a stable public deployment, put the service behind HTTPS, configure origin restrictions for the actual frontend domain, and use a persistent deployment rather than a temporary Quick Tunnel.

## Deploy on the IBM Z / LinuxONE VM

Use the [Windows SSH and Ubuntu/LinuxONE runbook](../deploy/ibm-linuxone/README.md), which uses the local key file `FloodWatchKey.pem` without adding it to the repository. The API service remains on `127.0.0.1:8000`; it is separate from GitHub Pages.

To enable on-demand regional inference on the VM, run the ML runner's `setup`, `preflight` and `train` modes. The API endpoint `/api/v1/models/regional-discharge/forecast` looks for the normalized CWC/NWDP archive, model weights, scalers, report, and the ML virtual environment. When ready, it invokes `predict_regional_lstm.py` and returns the seven-day discharge forecast. It returns a clear HTTP 503 if assets are missing; it does not invent fallback predictions.

The browser frontend now supports an optional LSTM map-colour contribution. In the **Regional LSTM risk contribution** panel, set the public HTTPS backend base URL and connect. The page requests `/api/v1/models/status` and `/api/v1/models/regional-discharge/forecast?all_stations=true`; recent station forecasts with coordinates and a station-relative discharge rank can modify nearby cells by up to 25%, fading to zero at 65 km. Disconnecting or leaving the URL blank keeps the existing rainfall/GloFAS-only colours. The distance rule is a coarse proximity heuristic, not validated river-network routing.

This is still an experimental risk score, **not calibrated flood probability**. The LSTM predicts discharge only, does not consume future rainfall forcing, and its station-relative percentile is not a flood-event probability. Flood-probability calibration needs independently sourced flood-event and non-event labels, chronological validation and reliability/Brier-score evaluation before such a probability label is justified. The API does not issue official warnings, water levels, inundation maps or evacuation recommendations.

## Install dependencies and run backend tests

For a clean development environment, install runtime requirements with:

```bash
python -m pip install -r backend/requirements.txt
```

To run the API test suite locally from the repository root:

```bash
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q backend/tests
```

A GitHub Actions workflow runs these tests when backend source, tests, requirements or the workflow itself change: [Test FloodWatch backend](../.github/workflows/backend-tests.yml).

The tests mock the upstream weather request; they validate the API contract and error handling without depending on external weather availability.

## Smoke tests

On the Linux server, in a second SSH session:

```bash
curl --max-time 10 http://127.0.0.1:8000/health
curl --max-time 15 http://127.0.0.1:8000/api/v1/status
curl --max-time 15 "http://127.0.0.1:8000/api/v1/weather?latitude=19.15&longitude=77.30"
curl --max-time 20 "http://127.0.0.1:8000/api/v1/river-flow?latitude=19.15&longitude=77.30"
curl --max-time 15 "http://127.0.0.1:8000/api/v1/water-observations?latitude=19.15&longitude=77.30&radius_km=100&limit=5"
curl --max-time 10 http://127.0.0.1:8000/api/v1/models/status
```

From Windows PowerShell, test via the current HTTPS Quick Tunnel:

```powershell
curl.exe --max-time 15 "https://YOUR-CURRENT-TUNNEL.trycloudflare.com/api/v1/weather?latitude=19.15&longitude=77.30"
```

Replace the example hostname with the current URL printed by `cloudflared`. A Quick Tunnel hostname is temporary and may change when a new tunnel is created.

## Deployment and security notes

- The service uses Python's standard library for the Open-Meteo request; FastAPI and Uvicorn are the server dependencies.
- Browser CORS access is limited to the project's GitHub Pages origin and localhost development origins.
- This unauthenticated demo API is public while exposed by a tunnel. Do not put secrets, private information, or patient data here.
- Cloudflare Quick Tunnels have no uptime guarantee. Use a stable HTTPS deployment and stricter service controls before a public production release.
