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

The event VM specification is Ubuntu 24.04, 3 vCPUs, 8 GiB RAM and a 50 GB root disk. It can host the lightweight FastAPI service and may run the regional LSTM if the installed Python/PyTorch runtime passes the on-machine checks. The VM label alone does not prove architecture, and a GitHub Actions pass does not prove the server has been deployed.

The current official [PyTorch CPU wheel index](https://download.pytorch.org/whl/cpu/torch/) lists `torch 2.10.0+cpu` wheels for CPython 3.12 on `linux_s390x`. The repository's ML setup now uses that official CPU index and validates imports/API support. This is a concrete path to running inference/training on IBM Z; the actual VM still has to pass `setup`, `preflight` and `train` before the submission claims it ran there.

Use the [Windows SSH + LinuxONE deployment runbook](../deploy/ibm-linuxone/README.md). It references the user's local key filename `FloodWatchKey.pem` in a PowerShell command. The SSH private key must stay on the user's computer; never commit or upload it. The VM user/IP need to match the instance's connection instructions.

### Deploy the service and run the model

From the checked-out repository root on the VM:

```bash
bash deploy/ibm-linuxone/install-user-service.sh
bash deploy/ibm-linuxone/run-regional-lstm.sh setup
bash deploy/ibm-linuxone/run-regional-lstm.sh preflight
bash deploy/ibm-linuxone/run-regional-lstm.sh train
```

The installer runs FastAPI in a lightweight virtual environment at `127.0.0.1:8000`. The regional ML runner builds a separate virtual environment, retrieves/normalizes CWC/NWDP-derived data, trains the regional model, evaluates it against persistence, and creates saved weights/scalers/report plus a research-forecast JSON output. Keep the full command output for judging evidence. A failed `preflight` is a blocker, not a successful IBM Z ML deployment.

Check the API on the VM:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/v1/status
curl -fsS http://127.0.0.1:8000/api/v1/models/status
curl -fsS --max-time 45 http://127.0.0.1:8000/api/v1/models/regional-discharge/forecast
```

The last endpoint invokes the regional LSTM using local saved weights and normalized history if all runtime files are present. It returns discharge forecasts, not water-level estimates, flood probabilities, inundation depth, or an official alert. It caches repeated inference for ten minutes. The frontend risk contours are still a separate index and do not consume this neural-network output. The response's history freshness is based on source timestamps; it cannot independently verify that a river sensor is transmitting now.

### Secure public demo connection

GitHub Pages remains separate from the VM service. To demonstrate the API from the public webpage, expose the service through an approved HTTPS reverse proxy or tunnel and configure its exact origin in the frontend. Do not expose port 8000 directly to the public Internet, put credentials in the repository, or hard-code a temporary tunnel URL. If the API or model assets are not available, the UI should report that status rather than silently inventing a prediction.

Before claiming IBM Z deployment, record `uname -m`, Python/NumPy/pandas/PyTorch versions, successful `/health` and `/api/v1/status` responses, and a successful forecast response from the VM. Until those command outputs are captured, the VM deployment remains pending even though the repository includes the runbook and endpoint.
 
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
