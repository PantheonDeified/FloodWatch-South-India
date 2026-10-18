# FloodWatch API backend

This folder contains the versioned FastAPI service source.

## Endpoint summary

- `GET /` — basic service information.
- `GET /health` — health check.
- `GET /api/v1/status` — provider and capability status.
- `GET /api/v1/water-observations?state=Kerala&limit=100` — paginated published NWDP/NWIC snapshot with optional state, measurement kind, freshness and search filters. If the repo data file is absent on the server, it fetches the public snapshot from GitHub and caches it for five minutes.
- `GET /api/v1/models/status` — model readiness report; confirms whether a locally trained forecast is available and lists prerequisites.
- `GET /api/v1/weather?latitude=19.15&longitude=77.30` — current Open-Meteo model conditions and two days of hourly forecast for coordinates within the prototype's South India coverage (latitude 7–21.8, longitude 73–87).

The water endpoint returns source-reported measurements and labels freshness unknown if a naive timestamp has no reliable timezone. A snapshot's generation time is not the same as the time of every measurement.

The weather response preserves Open-Meteo's normal response fields (`current`, `hourly`, `timezone`) and adds a `_floodwatch` metadata object. The values are gridded model estimates and forecasts, not direct measurements from a local station. This API does not issue a flood probability or official warning.

## Update the existing IBM LinuxONE server

The running service is separate from GitHub Pages. Updating this source file in GitHub does not automatically update the Linux server.

1. Open a Windows PowerShell session and connect to `linux1@148.100.98.93` with your existing SSH key.
2. In the Linux shell, check whether Uvicorn is already running with `pgrep -af 'uvicorn main:app'`. If a process is running, stop that specific PID with `kill <PID>` before starting another one. Do not kill unrelated processes.
3. Run these commands in the Linux shell, one at a time:

```bash
cd ~/floodwatch-api
source .venv/bin/activate
cp main.py "main.py.backup.$(date +%Y%m%d-%H%M%S)"
curl -fL "https://raw.githubusercontent.com/PantheonDeified/FloodWatch-South-India/main/backend/main.py" -o main.py.new
python -m py_compile main.py.new
mv main.py.new main.py
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

4. Keep the Linux terminal running Uvicorn while testing. Run the Cloudflare Quick Tunnel separately in the Windows PowerShell window where you launch `cloudflared`. If compilation fails, do not replace the running source; share the error and restore the backup if needed. Updating GitHub does not automatically update the Linux server.

## Recommended: keep the API running with systemd

The included service file assumes the server account is `linux1` and the application directory is `/home/linux1/floodwatch-api`. It restarts Uvicorn if it crashes and starts the API at boot. Updating code in GitHub still requires pulling/downloading the latest `main.py` onto the server.

After updating `main.py` and compiling it successfully, use these steps on the Linux server. First inspect any existing Uvicorn process; if one is still running from an earlier `nohup` command, stop only that process before enabling the service so port 8000 is not already occupied.

```bash
pgrep -af '[u]vicorn main:app' || true
# If the command above shows an old Uvicorn PID, stop that specific PID:
# kill <PID>
curl -fL "https://raw.githubusercontent.com/PantheonDeified/FloodWatch-South-India/main/backend/floodwatch-api.service" -o /tmp/floodwatch-api.service
sudo install -m 644 /tmp/floodwatch-api.service /etc/systemd/system/floodwatch-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now floodwatch-api
sudo systemctl status --no-pager floodwatch-api
curl --max-time 10 http://127.0.0.1:8000/health
```

If it does not start, inspect the logs with `sudo journalctl -u floodwatch-api -n 60 --no-pager`. Keep the Cloudflare Quick Tunnel running separately on your Windows computer when you need HTTPS access during the demo.

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
curl --max-time 15 "http://127.0.0.1:8000/api/v1/weather?latitude=19.15&longitude=77.30"
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
