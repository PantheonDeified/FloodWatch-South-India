#!/usr/bin/env bash
# Install/run the lightweight FloodWatch API as a per-user systemd service.
# Deliberately does not install PyTorch or expose the API on a public interface.
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
VENV="${FLOODWATCH_API_VENV:-$HOME/.local/share/floodwatch-api/venv}"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/floodwatch-api.service"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "ERROR: python3 is required. Install Python 3 and python3-venv first." >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemd/systemctl is required for this installer." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required for the local health check." >&2
  exit 1
fi

"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required.")
print("Python:", sys.version.split()[0])
PY
printf 'CPU architecture: '
uname -m
printf 'Repository: %s\n' "$ROOT_DIR"
printf 'Virtual environment: %s\n' "$VENV"

mkdir -p "$(dirname "$VENV")" "$UNIT_DIR"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$ROOT_DIR/backend/requirements.txt"
"$VENV/bin/python" -m py_compile "$ROOT_DIR/backend/main.py"

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=FloodWatch South India API (user service)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now floodwatch-api.service

healthy=0
for attempt in $(seq 1 20); do
  if curl --fail --silent --show-error http://127.0.0.1:8000/health; then
    printf '\nPASS: FloodWatch API health endpoint responded.\n'
    healthy=1
    break
  fi
  sleep 1
done
if [ "$healthy" -ne 1 ]; then
  echo "ERROR: API did not become healthy. Recent service logs:" >&2
  systemctl --user --no-pager --full status floodwatch-api.service || true
  journalctl --user -u floodwatch-api.service -n 60 --no-pager || true
  exit 1
fi

echo
echo "API status:"
curl --fail --silent --show-error http://127.0.0.1:8000/api/v1/status
echo
echo
echo "Model readiness (informational):"
curl --fail --silent --show-error http://127.0.0.1:8000/api/v1/models/status
echo
echo
echo "Service installed. Manage it with:"
echo "  systemctl --user status floodwatch-api"
echo "  journalctl --user -u floodwatch-api -f"
echo
echo "Security: service binds to 127.0.0.1 only. Do not expose port 8000 directly."
echo "For service survival after logout, ask the VM admin to enable systemd user lingering."
echo "This deploys the API; it does not deploy or certify the research LSTM."
