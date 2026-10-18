# FloodWatch South India — IBM Z Datathon demo guide

## 30-second pitch

FloodWatch is a source-aware flood-situational-awareness prototype for five South Indian states. It brings together gridded rainfall forecasts, modelled river discharge, timestamped water observations, generalized watershed context, and documented public-infrastructure evidence on one map. It helps a human reviewer see **where the evidence is changing and why**; it does not claim a calibrated flood probability, measure dam strength, or issue evacuation warnings.

## What is implemented today

- A browser-based dashboard hosted on GitHub Pages, with location search, optional browser geolocation, weather/rain overlays, station observations, and a region-wide map.
- A continuously interpolated risk surface with connected amber/red threshold contours. Colours are computed from source-reported numerical inputs; unknown or insufficient evidence must remain unknown rather than being silently interpreted as safe.
- A separate NASA GPM IMERG precipitation-rate imagery layer and an on-demand NASA GIBS / IMD endpoint check. Official bulletin/API values are not mixed into the score without source, time, units, geography and meaning checks.
- A research notebook for dated, geolocated, HTTPS-linked infrastructure evidence. Corroboration requires different publishing hosts. Inspections, normal dam operations and unverified reports are not automatically treated as hazards.
- A HydroBASINS level-6 context layer. Its `NEXT_DOWN` chain gives upstream/downstream **candidates**, not proof of a river-channel connection. The bundled file's current metadata says 100 polygons; regenerate and review it before claiming complete catchment coverage.
- A regional five-state discharge LSTM experiment with a chronological validation-selected blend against a persistence baseline. The chosen 25% LSTM / 75% persistence blend achieved a recorded pooled held-out RMSE of 649.63 m³/s vs 700.88 m³/s for persistence. The raw LSTM by itself was worse (830.45 m³/s). These are discharge-prediction metrics, not flood-probability metrics.

## Three-minute live demo

**0:00–0:20 — The problem.**  
Flood evidence is fragmented across weather forecasts, river gauges, satellite products and infrastructure reports. FloodWatch puts those sources on one map while keeping their provenance and uncertainty visible.

**0:20–0:45 — Choose a place.**  
Open the hosted site, select a location on the map or search for a South Indian district. Show the current weather-model fields and their source/model timestamp. Say explicitly that gridded weather is not a direct gauge observation.

**0:45–1:15 — Show the map.**  
Choose *Continuous risk contours · FloodWatch*. Explain green/amber/red as an experimental index (low/elevated/high signal), not percentages or official alert levels. Click a spot to inspect the component evidence. Point out that grey/unknown is intentional when inputs are missing.

**1:15–1:35 — Cross-check an observation.**  
Open the station list and read the source link, observation timestamp and freshness label. Do not describe a snapshot as real-time unless the individual observation's timestamp supports that.

**1:35–1:55 — Satellite and official feeds.**  
Select *NASA IMERG* to show precipitation-rate imagery, then click *Check NASA GIBS + IMD feeds*. Explain that browser CORS/authentication restrictions may show “could not verify”; that is not proof the provider is offline. The feed check is not an automatic alert source.

**1:55–2:15 — Basin and human infrastructure.**  
Show the basin-context panel and its `NEXT_DOWN` relationship label. Say “upstream candidate” rather than “confirmed upstream.” Briefly show the evidence notebook: coordinates, primary source, independent source and hydrology-link gate prevent a bare claim about a dam or embankment from changing the score.

**2:15–2:40 — Machine learning.**  
Show the ML validation card. The raw LSTM was less accurate than persistence, so the program selected a mix using validation data only. On the recorded held-out test set, the selected blend's pooled RMSE was 7.3% below persistence. The neural network does not colour the live map and is not approved for warnings; this is an explicit model-quality safeguard.

**2:40–3:00 — Why IBM Z.**  
Explain the intended platform role: a stable, auditable backend for source ingestion, data-quality checks, reproducible inference and API delivery, with the browser remaining a thin visualization client. The current static site is on GitHub Pages; do not say it is already deployed to IBM LinuxONE. Verify the VM's CPU architecture first and prove actual API health from the VM before claiming an IBM Z deployment.

## IBM Z / LinuxONE deployment status

The provided event VM specification is Ubuntu 24.04, 3 vCPUs, 8 GiB RAM and a 50 GB root disk. That is sufficient for the FastAPI data API and lightweight data-quality jobs. It is not evidence by itself of the processor architecture, and it is not a reason to assume a PyTorch build is available.

The website is deployed independently on GitHub Pages. The backend is a separate FastAPI application under `backend/`; training code currently runs in GitHub Actions and produces a research artifact. The repository now includes a [user-service installer and Ubuntu/LinuxONE runbook](../deploy/ibm-linuxone/README.md); it deploys the API on localhost and checks the health endpoints without installing PyTorch. The LSTM is not served by the backend or wired to the map score.

Run these **read-only** checks in the Ubuntu VM before installing any machine-learning dependency:

```
uname -m
lscpu
python3 --version
df -h /
free -h
```

- If `uname -m` returns `s390x`, this is an IBM Z architecture environment. Confirm the required Python wheels support it before attempting PyTorch installation. Keep API deployment separate from experimental model training if they do not.
- If it returns `x86_64` or another architecture, report the actual result accurately; do not infer the processor from the project name or VM label.
- Never paste an SSH private key, cloud password, API credential, or access token into the project repository or presentation.

### Run a local API smoke check on the VM

From a checkout of the repository, in the repository root:

```
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m py_compile backend/main.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal on the same VM:

```
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/v1/status
curl -fsS 'http://127.0.0.1:8000/api/v1/models/status'
```

Do not expose port 8000 directly to the public Internet. For an external browser demo, use an approved HTTPS reverse proxy/tunnel and restrict CORS to the exact front-end origin. A temporary tunnel is not a production deployment. The frontend's optional API setting can then be tested against the returned HTTPS origin.

## Architecture for the judging discussion

```
Public data providers
  ├─ Weather forecast / rainfall probability
  ├─ Modelled river-flow forecast
  ├─ Timestamped NWDP/CWC-derived observations
  ├─ NASA precipitation imagery + official IMD references
  └─ Human-reviewed infrastructure evidence
                 |
                 v
     Validation + provenance gates
     (unit, timestamp, location, freshness, uncertainty)
                 |
         +-------+------------------+
         |                          |
         v                          v
  Experimental risk index    Offline/CI discharge ML
  + continuous contours      LSTM vs persistence baseline
         |                          |
         +----------+---------------+
                    v
            Browser dashboard
        + source / limitations UI

  Target IBM Z VM role: durable API + scheduled collection,
  quality reporting and reproducible service operation.
  Current reality: GitHub Pages frontend; experimental ML runs in CI.
```

## Claims to avoid

- Do not call a score of 65 “65% flood probability.” It is not calibrated.
- Do not call HydroBASINS `NEXT_DOWN` a confirmed river route.
- Do not claim dam structural strength is measured; the notebook stores public evidence and does not calculate engineering safety.
- Do not say the ML model itself beat persistence: the raw LSTM did not in the recorded test.
- Do not claim the current dashboard or LSTM is already running on IBM Z/LinuxONE until VM architecture, the backend health endpoint, and the deployment path have been independently checked.
- Do not present an on-demand endpoint reachability check as validation that a forecast is correct.

## Judge-ready summary

**Novelty:** source-aware evidence fusion, explicit unknown states, basin-context candidates and independent infrastructure corroboration—rather than a colour-only map.  
**ML discipline:** chronological validation selects blend weight; the held-out test set is for evaluation, and the persistence baseline is reported next to the network.  
**Next milestone:** verify the event VM architecture, start and test the FastAPI service on it, then connect the hosted front end through HTTPS and record the live health/status response for the demo.
