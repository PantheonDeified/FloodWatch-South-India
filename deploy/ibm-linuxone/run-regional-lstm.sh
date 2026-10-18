#!/usr/bin/env bash
# Optional regional LSTM runner. This does not connect the LSTM to public warning outputs.
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCH="$(uname -m)"
DEFAULT_VENV="${HOME}/.local/share/floodwatch-regional-ml/venv"
MODE="${1:-preflight}"
shift || true

if [[ "$MODE" == "--help" || "$MODE" == "help" ]]; then
  cat <<'HELP'
Usage:
  bash deploy/ibm-linuxone/run-regional-lstm.sh setup
  bash deploy/ibm-linuxone/run-regional-lstm.sh preflight
  bash deploy/ibm-linuxone/run-regional-lstm.sh train

Optional environment:
  FLOODWATCH_ML_PYTHON=/path/to/python
  FLOODWATCH_MAX_RESOURCES=50
  FLOODWATCH_SKIP_DOWNLOAD=1  # use existing normalized data only

The pipeline is tested with Python 3.12 and PyTorch 2.10 on the GitHub Actions
runner. Setup installs dependencies automatically on common x86_64 Linux hosts.
On s390x, it deliberately refuses to install an unverified PyTorch wheel.
HELP
  exit 0
fi

if [[ -n "${FLOODWATCH_ML_PYTHON:-}" ]]; then
  PYTHON_BIN="$FLOODWATCH_ML_PYTHON"
elif [[ -x "$DEFAULT_VENV/bin/python" ]]; then
  PYTHON_BIN="$DEFAULT_VENV/bin/python"
else
  PYTHON_BIN="python3"
fi

case "$MODE" in
  setup)
    if [[ "$ARCH" == "s390x" ]]; then
      cat >&2 <<'MSG'
SETUP STOPPED SAFELY: this host reports s390x. The normal requirements file
pins the pipeline to PyTorch >=2.2, while IBM's publicly documented prebuilt
PyTorch-on-Z wheel page currently lists a much older CPU-only 1.10 wheel for
Python 3.6–3.9. That older build has not been qualified against this regional
pipeline. This script will not silently install a mismatched wheel.

Keep the model run reproducible using the repository's "Train FloodWatch
regional discharge LSTM" GitHub Actions workflow, or install a verified
s390x-compatible PyTorch >=2.2 build first and set FLOODWATCH_ML_PYTHON.
IBM reference: https://ibm.github.io/pytorch-on-z/
MSG
      exit 2
    fi
    if ! command -v python3 >/dev/null 2>&1; then
      echo "ERROR: python3 is required." >&2
      exit 1
    fi
    python3 -m venv "$DEFAULT_VENV"
    "$DEFAULT_VENV/bin/python" -m pip install --upgrade pip
    "$DEFAULT_VENV/bin/python" -m pip install -r "$ROOT_DIR/data_pipeline/requirements-ml.txt"
    echo "ML environment ready at: $DEFAULT_VENV"
    echo "Next: FLOODWATCH_ML_PYTHON='$DEFAULT_VENV/bin/python' bash deploy/ibm-linuxone/run-regional-lstm.sh preflight"
    exit 0
    ;;
  preflight|train)
    ;;
  *)
    echo "ERROR: unknown mode '$MODE'. Use setup, preflight, train, or --help." >&2
    exit 2
    ;;
esac

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY'
import sys
try:
    import numpy, pandas, torch
except Exception as exc:
    print(f"Missing or unimportable ML dependency: {exc}", file=sys.stderr)
    raise SystemExit(2)
version = tuple(int(part) for part in torch.__version__.split("+")[0].split(".")[:2])
print(f"Python {sys.version.split()[0]}")
print(f"NumPy {numpy.__version__} · pandas {pandas.__version__} · PyTorch {torch.__version__}")
if version < (2, 2):
    print("This pipeline requires PyTorch >=2.2; the older installed build is not qualified.", file=sys.stderr)
    raise SystemExit(3)
for attr in ("inference_mode", "set_num_threads", "set_num_interop_threads"):
    if not hasattr(torch, attr):
        print(f"PyTorch is missing required API: torch.{attr}", file=sys.stderr)
        raise SystemExit(4)
PY
then
  status=$?
  if [[ "$ARCH" == "s390x" ]]; then
    cat >&2 <<'MSG'
This IBM Z/LinuxONE host cannot yet run the regional LSTM with the Python/PyTorch
environment currently selected. Do not install an x86_64 wheel. Keep the
regional training/inference in GitHub Actions, whose current workflow is tested,
and run the lightweight FastAPI service on this VM. See:
  https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/train-regional-lstm.yml
  https://ibm.github.io/pytorch-on-z/
MSG
  else
    echo "Install the ML requirements with: bash deploy/ibm-linuxone/run-regional-lstm.sh setup" >&2
  fi
  exit "${status:-2}"
fi

if [[ "$MODE" == "preflight" ]]; then
  "$PYTHON_BIN" -m py_compile \
    "$ROOT_DIR/data_pipeline/scripts/train_regional_lstm.py" \
    "$ROOT_DIR/data_pipeline/scripts/predict_regional_lstm.py"
  echo "PASS: selected Python/PyTorch runtime can import required APIs and compile the pipeline."
  echo "To train and evaluate, run: bash deploy/ibm-linuxone/run-regional-lstm.sh train"
  exit 0
fi

RAW_DIR="$ROOT_DIR/data_pipeline/raw/nwdp_history"
OUTPUT_DIR="$ROOT_DIR/data_pipeline/output"
NORMALIZED="$OUTPUT_DIR/cwc_discharge_normalized.csv"
QUALITY_REPORT="$OUTPUT_DIR/cwc_discharge_quality_report.json"
MODEL_DIR="$OUTPUT_DIR/regional_models"
mkdir -p "$RAW_DIR" "$OUTPUT_DIR" "$MODEL_DIR"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-2}"

if [[ "${FLOODWATCH_SKIP_DOWNLOAD:-0}" != "1" ]]; then
  "$PYTHON_BIN" "$ROOT_DIR/data_pipeline/scripts/download_nwdp_history.py" \
    --out-dir "$RAW_DIR" \
    --keywords "river discharge" \
    --start-year 1950 \
    --end-year "$(date -u +%Y)" \
    --max-resources "${FLOODWATCH_MAX_RESOURCES:-50}"
  "$PYTHON_BIN" "$ROOT_DIR/data_pipeline/scripts/normalize_cwc_discharge.py" \
    --input-dir "$RAW_DIR" --output "$NORMALIZED" --report "$QUALITY_REPORT"
elif [[ ! -s "$NORMALIZED" ]]; then
  echo "ERROR: FLOODWATCH_SKIP_DOWNLOAD=1 but $NORMALIZED is missing/empty." >&2
  exit 1
fi

"$PYTHON_BIN" "$ROOT_DIR/data_pipeline/scripts/train_regional_lstm.py" \
  --observations "$NORMALIZED" --output-dir "$MODEL_DIR" \
  --lookback-days 90 --lead-days 7 --window-stride 14 \
  --epochs 6 --patience 2 --max-windows-per-station-split 70 \
  --hidden-size 48 --num-layers 1 --batch-size 512

"$PYTHON_BIN" "$ROOT_DIR/data_pipeline/scripts/predict_regional_lstm.py" \
  --observations "$NORMALIZED" \
  --model-file "$MODEL_DIR/regional_discharge_lstm.pt" \
  --scalers-file "$MODEL_DIR/regional_discharge_lstm.scalers.json" \
  --report-file "$MODEL_DIR/regional_discharge_lstm.report.json" \
  --output-file "$MODEL_DIR/latest_forecast_research.json" \
  --lookback-days 90

echo
echo "PASS: training, validation selection, held-out evaluation and saved-weight inference completed."
echo "Artifacts: $MODEL_DIR"
echo "This is research-only discharge prediction; it is not a flood probability and is not an official warning."
