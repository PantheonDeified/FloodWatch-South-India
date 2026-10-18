# FloodWatch API backend

This folder contains the versioned FastAPI service source.

## Endpoint summary

- `GET /` — basic service information.
- `GET /health` — health check.
- `GET /api/v1/status` — provider and capability status.
- `GET /api/v1/weather?latitude=19.15&longitude=77.30` — current Open-Meteo model conditions and two days of hourly forecast for coordinates within the prototype's South India coverage (latitude 7–21.8, longitude 73–87).

The weather response preserves Open-Meteo's normal response fields (`current`, `hourly`, `timezone`) and adds a `_floodwatch` metadata object. The values are gridded model estimates and forecasts, not direct measurements from a local station. This API does not issue a flood probability or official warning.

## Update the existing IBM LinuxONE server

The running service is separate from GitHub Pages. Updating this source file in GitHub does not automatically update the Linux server.

1. Keep your SSH session to `linux1@148.100.98.93`.
2. Stop the current foreground Uvicorn process with **Ctrl+C** in the Linux terminal where it is running.
3. Run these commands in the Linux shell, one at a time:

```bash
cd ~/floodwatch-api
cp main.py "main.py.backup.$(date +%Y%m%d-%H%M%S)"
curl -fL "https://raw.githubusercontent.com/PantheonDeified/FloodWatch-South-India/main/backend/main.py" -o main.py.new
python -m py_compile main.py.new
mv main.py.new main.py
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

4. Keep Uvicorn and the Cloudflare Quick Tunnel running while testing. If the Python compilation fails, do not replace the backup; share the error and restore the backup if needed.

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
