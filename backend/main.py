"""FloodWatch South India API.

A small public-data API for the FloodWatch browser frontend.
This service proxies Open-Meteo weather for South India and labels model data
as estimates. It does not calculate or issue flood warnings.
"""
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

APP_VERSION = "0.5.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = REPO_ROOT / "data" / "water-observations.json"
SNAPSHOT_URL = "https://raw.githubusercontent.com/PantheonDeified/FloodWatch-South-India/main/data/water-observations.json"
REGIONAL_MODEL_DIR = Path(os.environ.get(
    "FLOODWATCH_REGIONAL_MODEL_DIR",
    str(REPO_ROOT / "data_pipeline" / "output" / "regional_models"),
)).expanduser()
REGIONAL_OBSERVATIONS = Path(os.environ.get(
    "FLOODWATCH_REGIONAL_OBSERVATIONS",
    str(REPO_ROOT / "data_pipeline" / "output" / "cwc_discharge_normalized.csv"),
)).expanduser()
REGIONAL_ML_PYTHON = Path(os.environ.get(
    "FLOODWATCH_ML_PYTHON",
    str(Path.home() / ".local" / "share" / "floodwatch-regional-ml" / "venv" / "bin" / "python"),
)).expanduser()
REGIONAL_MODEL_FILE = REGIONAL_MODEL_DIR / "regional_discharge_lstm.pt"
REGIONAL_SCALERS_FILE = REGIONAL_MODEL_DIR / "regional_discharge_lstm.scalers.json"
REGIONAL_REPORT_FILE = REGIONAL_MODEL_DIR / "regional_discharge_lstm.report.json"
REGIONAL_PREDICTOR = REPO_ROOT / "data_pipeline" / "scripts" / "predict_regional_lstm.py"
REGIONAL_INFERENCE_CACHE_TTL_SECONDS = 600
_regional_inference_cache: dict[str, tuple[float, dict]] = {}
_regional_inference_lock = threading.Lock()
logger = logging.getLogger(__name__)
_snapshot_cache = {"loaded_at": 0.0, "payload": None}
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"

app = FastAPI(
    title="FloodWatch South India API",
    description="Public-data backend for the FloodWatch South India situational-awareness prototype",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pantheondeified.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
    max_age=600,
)


@app.get("/")
def home():
    return {
        "project": "FloodWatch South India",
        "status": "online",
        "version": APP_VERSION,
        "message": "Backend API is running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION,
    }


@app.get("/api/v1/status")
def api_status():
    return {
        "project": "FloodWatch South India",
        "version": APP_VERSION,
        "weather_provider": "Open-Meteo",
        "weather_endpoint": "/api/v1/weather?latitude=<lat>&longitude=<lon>",
        "river_flow_endpoint": "/api/v1/river-flow?latitude=<lat>&longitude=<lon>",
        "water_observations_endpoint": "/api/v1/water-observations?limit=100",
        "model_readiness_endpoint": "/api/v1/models/status",
        "regional_discharge_forecast_endpoint": "/api/v1/models/regional-discharge/forecast",
        "water_observations": "Published GitHub Pages JSON snapshot; collector runs every six hours when scheduled execution succeeds; observation freshness varies by source",
        "flood_forecast_model": "External Open-Meteo Flood API/GloFAS proxy available; the five-state regional discharge LSTM has completed a historical holdout evaluation and can be invoked on demand at /api/v1/models/regional-discharge/forecast when local ML assets are installed. Outputs are discharge research forecasts, not flood probabilities or official warnings.",
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }



def load_water_snapshot() -> dict:
    """Load a committed snapshot when deployed with the repo; otherwise fetch the public snapshot."""
    import time

    configured = os.environ.get("FLOODWATCH_WATER_SNAPSHOT")
    path = Path(configured).expanduser() if configured else DEFAULT_SNAPSHOT
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail="The configured water snapshot could not be read.") from exc
    else:
        if _snapshot_cache["payload"] is not None and time.time() - _snapshot_cache["loaded_at"] < 300:
            return _snapshot_cache["payload"]
        request = Request(SNAPSHOT_URL, headers={"Accept": "application/json", "User-Agent": "FloodWatch-South-India/0.3"}, method="GET")
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail="The published water-observation snapshot is temporarily unavailable.") from exc
        _snapshot_cache.update({"loaded_at": time.time(), "payload": payload})
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise HTTPException(status_code=502, detail="The water snapshot has an unexpected data format.")
    return payload


def observation_age_hours(record: dict, now: datetime | None = None) -> float | None:
    """Return age only when timestamp timezone is explicit; never guess browser/local time."""
    raw = str(record.get("observed_at") or record.get("observed_at_raw") or "").strip()
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        zone = str(record.get("source_timezone") or "").strip()
        if not zone or zone.lower() in {"unknown", "unspecified", "not specified", "local", "n/a"}:
            return None
        try:
            from zoneinfo import ZoneInfo
            stamp = stamp.replace(tzinfo=ZoneInfo(zone))
        except Exception:
            return None
    return ((now or datetime.now(timezone.utc)) - stamp.astimezone(timezone.utc)).total_seconds() / 3600


@app.get("/api/v1/water-observations")
def water_observations(
    state: str | None = Query(None, max_length=80),
    kind: str | None = Query(None, max_length=80),
    freshness: str | None = Query(None, pattern="^(recent|delayed|stale|unknown)$"),
    search: str | None = Query(None, max_length=120),
    latitude: float | None = Query(None, ge=7.0, le=21.8),
    longitude: float | None = Query(None, ge=73.0, le=87.0),
    radius_km: float = Query(100.0, gt=0, le=500),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100000),
):
    """Return paginated source records; optional radius filtering uses only published coordinates."""
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Provide both latitude and longitude for nearby-station filtering.")
    snapshot = load_water_snapshot()
    records = snapshot["observations"]
    now = datetime.now(timezone.utc)
    filtered = []
    for row in records:
        if not isinstance(row, dict):
            continue
        if state and str(row.get("state") or "").casefold() != state.casefold():
            continue
        if kind and str(row.get("kind") or "").casefold() != kind.casefold():
            continue
        if search:
            haystack = " ".join(str(row.get(key) or "") for key in (
                "station_name", "station_id", "river", "basin", "district", "state", "source_name"
            ))
            if search.casefold() not in haystack.casefold():
                continue
        distance_km = None
        if latitude is not None and longitude is not None:
            try:
                station_lat, station_lon = float(row.get("latitude")), float(row.get("longitude"))
            except (TypeError, ValueError):
                continue
            if not (-90 <= station_lat <= 90 and -180 <= station_lon <= 180):
                continue
            from math import asin, cos, radians, sin, sqrt
            lat1, lat2 = radians(latitude), radians(station_lat)
            dlat, dlon = lat2 - lat1, radians(station_lon - longitude)
            haversine = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            distance_km = 6371.0 * 2 * asin(sqrt(min(1.0, haversine)))
            if distance_km > radius_km:
                continue
        age = observation_age_hours(row, now)
        if age is None or age < -1:
            bucket = "unknown"
        elif age < 24:
            bucket = "recent"
        elif age < 72:
            bucket = "delayed"
        else:
            bucket = "stale"
        if freshness and freshness != bucket:
            continue
        item = dict(row)
        item["freshness"] = bucket
        item["age_hours"] = round(max(0.0, age), 2) if age is not None and age >= 0 else None
        if distance_km is not None:
            item["distance_km"] = round(distance_km, 2)
        filtered.append(item)
    return {
        "generated_at_utc": snapshot.get("generated_at_utc"),
        "source_resource_count_checked": snapshot.get("resource_count_checked"),
        "total_records": len(filtered),
        "limit": limit,
        "offset": offset,
        "observations": filtered[offset:offset + limit],
        "metadata": {
            "source": "FloodWatch published NWDP/NWIC observation snapshot",
            "snapshot_time_is_not_each_reading_time": True,
            "timezone_ambiguous_records_are_freshness_unknown": True,
            "not_a_flood_warning": True,
        },
    }


@app.get("/api/v1/river-flow")
def get_river_flow(
    latitude: float = Query(..., ge=7.0, le=21.8, description="Latitude within the supported South India region"),
    longitude: float = Query(..., ge=73.0, le=87.0, description="Longitude within the supported South India region"),
):
    """Proxy the Open-Meteo Flood API/GloFAS context series; not a local FloodWatch prediction."""
    params = urlencode({
        "latitude": f"{latitude:.5f}",
        "longitude": f"{longitude:.5f}",
        "daily": "river_discharge",
        "past_days": "90",
        "forecast_days": "7",
        "timezone": "auto",
    })
    request = Request(
        f"{FLOOD_URL}?{params}",
        headers={"Accept": "application/json", "User-Agent": f"FloodWatch-South-India/{APP_VERSION}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo Flood API returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail="The river-flow model provider could not be reached.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="The river-flow provider returned an invalid response.") from exc
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list) or not isinstance(daily.get("river_discharge"), list):
        raise HTTPException(status_code=502, detail="The river-flow provider did not return a valid daily discharge series.")
    if len(daily["time"]) != len(daily["river_discharge"]) or not daily["time"]:
        raise HTTPException(status_code=502, detail="The river-flow provider returned mismatched or empty series.")
    payload["_floodwatch"] = {
        "backend_version": APP_VERSION,
        "provider": "Open-Meteo Flood API / GloFAS",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_type": "modelled river-discharge context, not a gauge observation or FloodWatch-trained prediction",
        "forecast_horizon_days": 7,
        "historical_context_days": 90,
    }
    return payload


def regional_inference_asset_status() -> dict:
    """Check local files only; this does not import PyTorch or imply model validity."""
    checks = {
        "ml_python_executable": REGIONAL_ML_PYTHON.is_file() and os.access(REGIONAL_ML_PYTHON, os.X_OK),
        "normalized_observations": REGIONAL_OBSERVATIONS.is_file(),
        "model_weights": REGIONAL_MODEL_FILE.is_file(),
        "scaler_metadata": REGIONAL_SCALERS_FILE.is_file(),
        "evaluation_report": REGIONAL_REPORT_FILE.is_file(),
        "predictor_script": REGIONAL_PREDICTOR.is_file(),
    }
    return {
        "required_assets_present": all(checks.values()),
        "asset_checks": checks,
    }


@app.get("/api/v1/models/status")
def model_status():
    """Report evaluation evidence and whether this machine has enough files for on-demand inference."""
    runtime = regional_inference_asset_status()
    assets_ready = runtime["required_assets_present"]
    return {
        "status": (
            "regional_lstm_local_inference_assets_ready"
            if assets_ready else
            "regional_lstm_evaluated_local_inference_assets_missing"
        ),
        "api_version": APP_VERSION,
        "regional_model": {
            "status": "historically_trained_and_evaluated; local inference is conditional on installed assets",
            "model_type": "regional multi-station masked-input LSTM with validation-selected persistence blend",
            "states": ["Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"],
            "source_station_count": 241,
            "stations_with_usable_windows": 231,
            "lookback_days": 90,
            "forecast_horizon_days": 7,
            "validation_blend_alpha": 0.25,
            "test_targets": 89824,
            "test_metrics_m3_s": {
                "selected_lstm_persistence_blend": {
                    "mae": 75.6971, "rmse": 649.6332, "nse": 0.6524
                },
                "raw_lstm": {
                    "mae": 90.0275, "rmse": 830.4477, "nse": 0.4320
                },
                "persistence_baseline": {
                    "mae": 79.8152, "rmse": 700.8768, "nse": 0.5954
                },
                "selected_blend_rmse_skill_vs_persistence": 0.0731
            },
            "validation_selection": {
                "method": "Choose the LSTM contribution alpha on the chronological validation split by RMSE; ties prefer persistence.",
                "alpha": 0.25,
                "test_set_used_for_selection": False
            },
            "training_duration_seconds_cached_fit": 21.53,
            "source_history_end_date": "2026-10-17",
            "training_run_url": "https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39126986154",
            "artifact_url": "https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39126986154/artifacts/12136079681",
            "artifact_note": "GitHub Actions artifacts can expire. The VM's own inference assets are checked separately below."
        },
        "single_station_test_metrics": {
            "station": "Yadgir, Karnataka",
            "target": "daily maximum river discharge in m3/s",
            "lstm_rmse_m3s": 1043.61,
            "persistence_rmse_m3s": 1274.75,
            "overall_rmse_skill_vs_persistence": 0.1813,
            "high_flow_nse": -0.0129,
            "note": "The single-station pilot's overall metric improved but high-flow performance remains weak."
        },
        "inference_endpoint_available": True,
        "inference_endpoint": "/api/v1/models/regional-discharge/forecast",
        "trained_model_artifact": (
            "Local model weights, scalers and report are present; run on-demand inference to verify runtime compatibility."
            if assets_ready else
            "not available as local server artifacts; the GitHub Actions artifact is temporary and may expire"
        ),
        "live_inference_available": False,
        "local_runtime_note": "On-demand inference is distinct from verified live sensor data; source-history age must be inspected.",
        "on_demand_inference_available": assets_ready,
        "model_served_by_api": assets_ready,
        "live_sensor_data_verified": False,
        "runtime_assets": runtime,
        "connected_to_frontend_risk_score": False,
        "validated_south_india_flood_forecast": False,
        "required_before_public_warning_use": [
            "validate predictions on independent gauges, years and verified flood events across the region",
            "align discharge and weather inputs with station/catchment metadata and confirmed units",
            "report per-station, per-horizon, high-flow skill and uncertainty",
            "verify input freshness and sensor/source transmission separately from file timestamps",
            "complete operational review, monitoring, rollback and publish the model card"
        ],
        "message": (
            "The API can run the saved regional LSTM on demand when the local ML virtualenv, normalized observations, weights, scalers and report are present. The returned value is discharge, not flood probability, water level or inundation. "
            "A chronological validation-selected 25% LSTM / 75% persistence blend improved pooled test RMSE by 7.3%, while raw LSTM predictions were worse than persistence. "
            "Inference is not used to colour the map or issue public warnings."
        )
    }


@app.get("/api/v1/models/regional-discharge/forecast")
def regional_discharge_forecast(
    station_id: str | None = Query(
        None, max_length=120,
        description="Optional exact station ID from the normalized CWC/NWDP history; omit to use the predictor's default eligible station.",
    ),
):
    """Run the saved regional discharge model on demand; never convert output into a flood probability."""
    chosen_station = (station_id or "").strip()
    if chosen_station and (chosen_station.startswith("-") or any(ord(char) < 32 for char in chosen_station)):
        raise HTTPException(status_code=422, detail="station_id contains unsupported characters.")

    cache_key = chosen_station or "__default_eligible_station__"

    def cached_response():
        cached = _regional_inference_cache.get(cache_key)
        if not cached:
            return None
        stored_at, stored_payload = cached
        if time.monotonic() - stored_at > REGIONAL_INFERENCE_CACHE_TTL_SECONDS:
            _regional_inference_cache.pop(cache_key, None)
            return None
        result = json.loads(json.dumps(stored_payload))
        result["serving_metadata"]["cache_hit"] = True
        result["serving_metadata"]["served_at_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    cached = cached_response()
    if cached is not None:
        return cached

    if not _regional_inference_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Another regional inference is running. Retry shortly; duplicate requests are intentionally throttled.",
        )
    try:
        # Re-check after acquiring the lock so concurrent requests share the same cached result.
        cached = cached_response()
        if cached is not None:
            return cached

        runtime = regional_inference_asset_status()
        if not runtime["required_assets_present"]:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Regional inference assets are not ready on this server.",
                    "asset_checks": runtime["asset_checks"],
                    "next_steps": [
                        "Run bash deploy/ibm-linuxone/run-regional-lstm.sh setup",
                        "Run bash deploy/ibm-linuxone/run-regional-lstm.sh preflight",
                        "Run bash deploy/ibm-linuxone/run-regional-lstm.sh train",
                        "Retry /api/v1/models/status and this endpoint after the run succeeds",
                    ],
                },
            )

        with tempfile.TemporaryDirectory(prefix="floodwatch-regional-inference-") as tmp_dir:
            output_file = Path(tmp_dir) / "forecast.json"
            command = [
                str(REGIONAL_ML_PYTHON),
                str(REGIONAL_PREDICTOR),
                "--observations", str(REGIONAL_OBSERVATIONS),
                "--model-file", str(REGIONAL_MODEL_FILE),
                "--scalers-file", str(REGIONAL_SCALERS_FILE),
                "--report-file", str(REGIONAL_REPORT_FILE),
                "--output-file", str(output_file),
                "--lookback-days", "90",
            ]
            if chosen_station:
                command.append(f"--station-id={chosen_station}")
            env = os.environ.copy()
            env.setdefault("OMP_NUM_THREADS", "2")
            env.setdefault("MKL_NUM_THREADS", "2")
            env.setdefault("OPENBLAS_NUM_THREADS", "2")
            env.setdefault("NUMEXPR_NUM_THREADS", "2")
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True, timeout=45,
                    check=False, env=env,
                )
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(
                    status_code=504,
                    detail="Regional discharge inference exceeded the 45-second limit; inspect VM CPU/memory and model logs.",
                ) from exc
            except OSError as exc:
                logger.exception("Could not start the configured regional ML Python executable.")
                raise HTTPException(
                    status_code=503,
                    detail="Could not start the configured regional ML runtime; inspect server configuration and logs.",
                ) from exc

            if completed.returncode != 0:
                logger.error(
                    "Regional inference failed (exit=%s): %s",
                    completed.returncode,
                    ((completed.stderr or completed.stdout or "no runtime details")[-1800:]),
                )
                raise HTTPException(
                    status_code=503,
                    detail="Regional inference failed. Run the ML preflight and inspect the API service journal for the underlying error.",
                )
            if not output_file.is_file():
                raise HTTPException(status_code=502, detail="Regional predictor finished without writing its output artifact.")
            try:
                payload = json.loads(output_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.exception("Regional predictor output could not be parsed.")
                raise HTTPException(status_code=502, detail="Regional predictor output was not valid JSON.") from exc

        predictions = payload.get("forecast") if isinstance(payload, dict) else None
        if not isinstance(predictions, list) or not predictions:
            raise HTTPException(status_code=502, detail="Regional predictor output is missing its forecast list.")
        for item in predictions:
            if not isinstance(item, dict):
                raise HTTPException(status_code=502, detail="Regional predictor output contains an invalid forecast row.")
            try:
                value = float(item["predicted_discharge_m3_s"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=502, detail="Regional forecast row is missing a numeric discharge prediction.") from exc
            if not math.isfinite(value) or value < 0:
                raise HTTPException(status_code=502, detail="Regional predictor output contains a non-finite or negative discharge prediction.")

        # Never expose absolute server paths from the local inference subprocess.
        payload.pop("model_artifact", None)
        payload.pop("scalers_artifact", None)
        payload["serving_metadata"] = {
            "inference_mode": "on-demand saved-weight inference",
            "served_at_utc": datetime.now(timezone.utc).isoformat(),
            "cache_ttl_seconds": REGIONAL_INFERENCE_CACHE_TTL_SECONDS,
            "cache_hit": False,
            "input_observations_file": "configured normalized CWC/NWDP history",
            "uses_future_rainfall_forcing": False,
            "is_flood_probability": False,
            "is_official_warning": False,
            "note": "forecast_is_live is a source-history age heuristic only; it does not verify live sensor transmission. Discharge is not water level or inundation depth.",
        }
        _regional_inference_cache[cache_key] = (time.monotonic(), payload)
        return json.loads(json.dumps(payload))
    finally:
        _regional_inference_lock.release()


@app.get("/api/v1/weather")
def get_weather(
    latitude: float = Query(..., ge=7.0, le=21.8, description="Latitude within the supported South India region"),
    longitude: float = Query(..., ge=73.0, le=87.0, description="Longitude within the supported South India region"),
):
    """Return Open-Meteo current conditions and two days of hourly forecast.

    Values are gridded weather-model estimates, not direct station observations.
    The coordinates are bounded to the prototype's South India coverage.
    """
    params = urlencode(
        {
            "latitude": f"{latitude:.5f}",
            "longitude": f"{longitude:.5f}",
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
                "precipitation,rain,showers,cloud_cover,wind_speed_10m,"
                "wind_gusts_10m,weather_code"
            ),
            "hourly": "temperature_2m,precipitation_probability,precipitation,rain",
            "forecast_days": "2",
            "timezone": "auto",
        }
    )
    request = Request(
        f"{WEATHER_URL}?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "FloodWatch-South-India/0.2 (public-data prototype)",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not return provider HTML or internal response details to the browser.
        raise HTTPException(
            status_code=502,
            detail=f"Open-Meteo returned HTTP {exc.code}. Try again shortly.",
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HTTPException(
            status_code=502,
            detail="The weather provider could not be reached. Try again shortly.",
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="The weather provider returned an invalid response.",
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise HTTPException(
            status_code=502,
            detail="The weather provider response did not include current conditions.",
        )

    # Preserve Open-Meteo's normal top-level fields so the existing frontend
    # can consume the response without a data-shape conversion.
    payload["_floodwatch"] = {
        "backend_version": APP_VERSION,
        "provider": "Open-Meteo",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_type": "gridded model estimate / forecast, not a station observation",
    }
    return payload
