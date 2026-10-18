# FloodWatch API backend

This folder contains the versioned FastAPI service source.

## Endpoint summary

- `GET /` — basic service information.
- `GET /health` — health check.
- `GET /api/v1/status` — provider and capability status.
- `GET /api/v1/river-flow?latitude=19.15&longitude=77.30` — 90-day historical context and 7-day Open-Meteo Flood API/GloFAS discharge series; this is modelled external data, not a locally trained FloodWatch prediction.
- `GET /api/v1/water-observations?state=Kerala&limit=100` — paginated published NWDP/NWIC snapshot with optional state, measurement kind, freshness, search, and nearby-coordinate/radius filters. Nearby results use only published station coordinates and include `distance_km`; records without usable coordinates are excluded. If the repo data file is absent on the server, it fetches the public snapshot from GitHub and caches it for five minutes.
- `GET /api/v1/models/status` — evaluation metrics plus a file-based readiness check for the local ML virtual environment, normalized observations, model weights, scalers and report.
- `GET /api/v1/models/regional-discharge/forecast` — runs the saved-weight regional LSTM on demand when those local assets exist; accepts an optional exact `station_id`, returns seven daily discharge estimates, caches per-station results for 10 minutes, and returns HTTP 503 when required assets are missing.
- `GET /api/v1/weather?latitude=19.15&longitude=77.30` — current Open-Meteo model conditions and two days of hourly forecast for coordinates within the prototype's South India coverage (latitude 7–21.8, longitude 73–87).

The water endpoint returns source-reported measurements and labels freshness unknown if a naive timestamp has no reliable timezone. A snapshot's generation time is not the same as the time of every measurement.

The weather response preserves Open-Meteo's normal response fields (`current`, `hourly`, `timezone`) and adds a `_floodwatch` metadata object. The values are gridded model estimates and forecasts, not direct measurements from a local station. This API does not issue a flood probability or official warning.

## Build a container image

From the repository root:

```bash
docker build -f backend/Dockerfile -t floodwatch-api:0.5.0 .
docker run --rm -p 8000:8000 floodwatch-api:0.3.0
```

The container runs as a non-root user and includes a health check. It fetches the published water snapshot from the repository because the image intentionally contains only the API source, not the full data directory. For a stable public deployment, put the service behind HTTPS, configure origin restrictions for the actual frontend domain, and use a persistent deployment rather than a temporary Quick Tunnel.

## Deploy on the IBM Z / LinuxONE VM

Use the [Windows SSH and Ubuntu/LinuxONE runbook](../deploy/ibm-linuxone/README.md), which uses the local key file `FloodWatchKey.pem` without adding it to the repository. The API service remains on `127.0.0.1:8000`; it is separate from GitHub Pages.

To enable on-demand regional inference on the VM, run the ML runner's `setup`, `preflight` and `train` modes. The API endpoint `/api/v1/models/regional-discharge/forecast` looks for the normalized CWC/NWDP archive, model weights, scalers, report, and the ML virtual environment. When ready, it invokes `predict_regional_lstm.py` and returns the seven-day discharge forecast. It returns a clear HTTP 503 if assets are missing; it does not invent fallback predictions.

This route is a software inference path, not validation of a flood-warning system. It is not connected to the frontend risk colours and does not return flood probability, water level, inundation or evacuation recommendations.

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
