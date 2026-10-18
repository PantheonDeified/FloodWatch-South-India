# IBM LinuxONE / Ubuntu 24.04 deployment

## One-command local API setup

On the event virtual server, first confirm the actual architecture and disk/RAM:

```bash
uname -m
lscpu
df -h /
free -h
```

From your checkout of this repository:

```bash
git pull origin main
bash deploy/ibm-linuxone/install-user-service.sh
```

The script creates a Python virtual environment under `~/.local/share/floodwatch-api/venv`, installs only the lightweight FastAPI requirements, installs a per-user systemd service, then verifies `/health`, `/api/v1/status`, and `/api/v1/models/status`. It deliberately does not install PyTorch, and does not overwrite the repository or publish server credentials.

If you have not cloned the public repository yet:

```bash
git clone https://github.com/PantheonDeified/FloodWatch-South-India.git
cd FloodWatch-South-India
bash deploy/ibm-linuxone/install-user-service.sh
```

## Service commands

```bash
systemctl --user status floodwatch-api
journalctl --user -u floodwatch-api -f
systemctl --user restart floodwatch-api
```

The service listens on `127.0.0.1:8000` only. This is intentional: never open port 8000 directly to the Internet. To demo the API from the public Pages website, use an approved HTTPS reverse proxy/tunnel, verify the backend CORS policy, and configure the frontend with that HTTPS origin. Treat a temporary tunnel as a demo link, not production infrastructure.

For the service to stay active after your SSH session ends, ask the VM administrator to enable systemd user lingering for your account. The installer does not need your cloud password, a private SSH key, or access tokens.

## IBM Z / ML note

The VM name does not prove the processor architecture. Record the output of `uname -m` in the submission. The API deployment uses FastAPI only; it is independent of the regional LSTM's PyTorch training environment, which currently runs in GitHub Actions. Do not claim the LSTM is running on IBM Z unless you build and run it on this server and attach reproducible logs. Current API deployment does not wire research-model output to public risk colours or alerts.
