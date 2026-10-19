# IBM LinuxONE / Ubuntu 24.04 deployment

This runbook deploys the lightweight FastAPI service first, then enables the regional discharge LSTM on the same VM when the ML runtime and training artifacts are ready. The model API endpoint serves discharge predictions only; it does not issue flood alerts or write to the map's risk score.

## 1. Connect from Windows with `FloodWatchKey.pem`

Run this in **Windows PowerShell on your own PC**, not inside the VM. Keep the key file on your PC; never upload it to GitHub or paste its contents into chat.

```powershell
$keyPath = Join-Path $HOME 'Downloads\FloodWatchKey.pem'  # change this if the file is stored elsewhere
$vmUser = 'linux1'                                        # use the SSH login shown by the VM console
$vmHost = 'YOUR_VM_PUBLIC_IP'                             # replace with this VM's public IP/DNS name

if (-not (Test-Path $keyPath)) { throw "SSH key not found: $keyPath" }
icacls $keyPath /inheritance:r
icacls $keyPath /grant:r "$($env:USERNAME):(R)"
ssh -o IdentitiesOnly=yes -i $keyPath "$vmUser@$vmHost"
```

Use the actual **SSH login username** and **public IP** shown in the instance's connection instructions; the IBM account/project email is not necessarily the Linux login. If PowerShell says the key is not found, change `$keyPath` to the actual path. If SSH returns a permission error, check the key ACL and the VM's configured public key.

## 2. Verify the actual VM architecture

Run these commands after connecting:

```bash
uname -m
lscpu
python3 --version
df -h /
free -h
```

An `s390x` result indicates IBM Z architecture. Record the output for your datathon notes; do not infer architecture from the VM flavour name alone.

## 3. Install and start the API

From the Linux shell:

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip curl
git clone https://github.com/PantheonDeified/FloodWatch-South-India.git
cd FloodWatch-South-India
bash deploy/ibm-linuxone/install-user-service.sh
```

If the repository is already cloned, use `cd ~/FloodWatch-South-India && git pull origin main` instead of cloning a second copy. The installer creates an API virtual environment under `~/.local/share/floodwatch-api/venv`, installs only `backend/requirements.txt`, and creates a user-level systemd service bound to `127.0.0.1:8000`. It does not install PyTorch.

Verify the service locally on the VM:

```bash
systemctl --user status floodwatch-api
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/v1/status
curl -fsS http://127.0.0.1:8000/api/v1/models/status
```

For service logs: `journalctl --user -u floodwatch-api -n 80 --no-pager`. To restart: `systemctl --user restart floodwatch-api`. To keep a user service running after logout, the VM administrator may need to enable systemd user lingering.

## 4. Enable on-demand regional LSTM inference

The official PyTorch CPU wheel index currently advertises `torch 2.10.0+cpu` wheels for CPython 3.12 on `linux_s390x`, as well as other common CPU platforms. That makes an IBM Z installation technically possible; it does **not** substitute for running preflight and training on this particular VM. See the [official PyTorch CPU wheel index](https://download.pytorch.org/whl/cpu/torch/).

From the repository root:

```bash
bash deploy/ibm-linuxone/run-regional-lstm.sh setup
bash deploy/ibm-linuxone/run-regional-lstm.sh preflight
bash deploy/ibm-linuxone/run-regional-lstm.sh train
systemctl --user restart floodwatch-api
```

- `setup` creates a separate ML virtual environment and installs NumPy, pandas, and the pinned CPU PyTorch wheel.
- `preflight` prints architecture/runtime versions and checks the required ML API and script syntax.
- `train` downloads and normalizes the available CWC/NWDP discharge sources, trains the five-state model, evaluates against persistence, saves weights/scalers/report, then runs saved-weight inference.
- Training outputs are written to `data_pipeline/output/regional_models/`; the normalized input is written to `data_pipeline/output/cwc_discharge_normalized.csv`.

Do not skip a failed preflight. If installation/import fails on `s390x`, keep the command output, try the setup step once more, and use the GitHub Actions training workflow as a fallback. Do not install an x86 wheel onto an IBM Z system.

### Call the trained model through the API

After `train` succeeds, restart the API so it loads the current route implementation, then check readiness:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/models/status
curl -fsS --max-time 45 http://127.0.0.1:8000/api/v1/models/regional-discharge/forecast
curl -fsS --max-time 60 "http://127.0.0.1:8000/api/v1/models/regional-discharge/forecast?all_stations=true" > /tmp/floodwatch-station-forecasts.json
```

The second endpoint runs the saved-weight predictor on demand. To target one particular station, add `?station_id=` and a **real ID from the normalized source file**; leaving it empty lets the predictor choose its default eligible station. Repeated requests for the same station are cached for 10 minutes to avoid repeatedly consuming the VM's 3 vCPUs.

The API returns seven daily discharge predictions when the pipeline's required local files and Python runtime are present. The `all_stations=true` form returns eligible station coordinates plus a station-relative percentile of predicted peak discharge against available station history. Check `station_id`, coordinates, `history_window_end`, `history_freshness`, `forecast_is_live`, and the source/model warning. Freshness is a timestamp-age heuristic, not proof of current sensor transmission. The optional frontend integration uses these percentiles as a distance-faded, at-most-25% modifier to its experimental risk score—not as flood probability or an official warning.

If the endpoint responds with HTTP 503, inspect `/api/v1/models/status`, run `preflight`, check that `data_pipeline/output/cwc_discharge_normalized.csv` and all model artifacts exist, then read the service journal. The API runtime is deliberately separate from the ML virtual environment.

## 5. Connect the website securely (optional demo step)

GitHub Pages is deployed independently from the VM. To make the browser call the API, expose it through an approved **HTTPS** reverse proxy or tunnel and configure the frontend with that HTTPS origin. The frontend stores the entered URL only in that browser's local storage.

- Do not expose port 8000 directly to the public Internet.
- Do not hard-code the tunnel URL into the repository; temporary Quick Tunnel names change.
- Do not put passwords, SSH private keys, API tokens or personal identifiers in the repository.
- The public demo API has no user authentication; never put sensitive information through it.
- GitHub Pages being green does not prove the VM service or model has been installed. Capture the actual VM health/inference output for the judging demo.

## 6. What to capture for judges

Record the following in a text file without credentials:

1. `uname -m`, Python version, free disk/RAM, and the printed NumPy/pandas/PyTorch versions.
2. `/health` and `/api/v1/status` JSON from the VM.
3. `/api/v1/models/status` before and after the regional training run.
4. The successful `preflight` and `train` output plus a sample `/api/v1/models/regional-discharge/forecast` response.
5. Model metrics and limitations from [the model card](../../data_pipeline/SUBMISSION_MODEL_CARD.md).

A working inference endpoint makes the pipeline demonstrable; scientific validation on independent flood events is a separate requirement before using the output for public warning decisions.
