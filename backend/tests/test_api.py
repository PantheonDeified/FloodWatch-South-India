from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main  # noqa: E402


client = TestClient(main.app)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


def example_provider_payload() -> dict:
    return {
        "latitude": 19.15,
        "longitude": 77.30,
        "timezone": "Asia/Kolkata",
        "current": {
            "time": "2026-10-18T08:00",
            "temperature_2m": 27.0,
            "relative_humidity_2m": 60,
            "precipitation": 0.0,
        },
        "hourly": {
            "time": ["2026-10-18T08:00", "2026-10-18T09:00"],
            "temperature_2m": [27.0, 29.0],
        },
    }


def test_health_is_healthy_and_versioned():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == main.APP_VERSION
    assert data["timestamp"]


def test_status_lists_weather_proxy():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["weather_provider"] == "Open-Meteo"
    assert data["version"] == main.APP_VERSION
    assert "/api/v1/weather" in data["weather_endpoint"]
    assert data["river_flow_endpoint"].startswith("/api/v1/river-flow")
    assert data["water_observations_endpoint"].startswith("/api/v1/water-observations")
    assert data["model_readiness_endpoint"] == "/api/v1/models/status"
    assert "GloFAS proxy available" in data["flood_forecast_model"]
    assert "completed a historical holdout evaluation" in data["flood_forecast_model"]
    assert "/api/v1/models/regional-discharge/forecast" in data["flood_forecast_model"]


def test_weather_returns_provider_payload_and_metadata(monkeypatch):
    monkeypatch.setattr(
        main,
        "urlopen",
        Mock(return_value=FakeResponse(example_provider_payload())),
    )
    response = client.get(
        "/api/v1/weather",
        params={"latitude": 19.15, "longitude": 77.30},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["current"]["temperature_2m"] == 27.0
    assert len(data["hourly"]["time"]) == 2
    assert data["_floodwatch"]["provider"] == "Open-Meteo"
    assert "not a station observation" in data["_floodwatch"]["data_type"]
    main.urlopen.assert_called_once()


def test_weather_rejects_coordinates_outside_supported_region(monkeypatch):
    urlopen = Mock()
    monkeypatch.setattr(main, "urlopen", urlopen)
    response = client.get(
        "/api/v1/weather",
        params={"latitude": 22.0, "longitude": 77.30},
    )
    assert response.status_code == 422
    urlopen.assert_not_called()


def test_weather_converts_upstream_http_error_to_502(monkeypatch):
    monkeypatch.setattr(
        main,
        "urlopen",
        Mock(side_effect=HTTPError("https://example.invalid", 503, "unavailable", None, None)),
    )
    response = client.get(
        "/api/v1/weather",
        params={"latitude": 19.15, "longitude": 77.30},
    )
    assert response.status_code == 502
    assert "Open-Meteo returned HTTP 503" in response.json()["detail"]


def test_weather_rejects_provider_payload_without_current_conditions(monkeypatch):
    monkeypatch.setattr(
        main,
        "urlopen",
        Mock(return_value=FakeResponse({"hourly": {"time": []}})),
    )
    response = client.get(
        "/api/v1/weather",
        params={"latitude": 19.15, "longitude": 77.30},
    )
    assert response.status_code == 502
    assert "did not include current conditions" in response.json()["detail"]


def test_model_status_reports_metrics_and_local_inference_readiness():
    response = client.get("/api/v1/models/status")
    assert response.status_code == 200
    data = response.json()
    expected_assets_ready = main.regional_inference_asset_status()["required_assets_present"]
    assert data["status"] == (
        "regional_lstm_local_inference_assets_ready"
        if expected_assets_ready else
        "regional_lstm_evaluated_local_inference_assets_missing"
    )
    assert data["validated_south_india_flood_forecast"] is False
    assert data["live_sensor_data_verified"] is False
    assert data["on_demand_inference_available"] is expected_assets_ready
    assert data["model_served_by_api"] is expected_assets_ready
    assert data["connected_to_frontend_risk_score"] is False
    assert data["inference_endpoint"] == "/api/v1/models/regional-discharge/forecast"
    regional = data["regional_model"]
    assert regional["states"] == [
        "Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"
    ]
    assert regional["test_targets"] == 89824
    assert regional["validation_blend_alpha"] == 0.25
    assert regional["validation_selection"]["test_set_used_for_selection"] is False
    metrics = regional["test_metrics_m3_s"]
    assert metrics["raw_lstm"]["rmse"] > metrics["persistence_baseline"]["rmse"]
    assert metrics["selected_lstm_persistence_blend"]["rmse"] < metrics["persistence_baseline"]["rmse"]
    assert metrics["selected_blend_rmse_skill_vs_persistence"] > 0.07
    assert "not available as local server artifacts" in data["trained_model_artifact"] or "Local model weights" in data["trained_model_artifact"]
    assert data["single_station_test_metrics"]["high_flow_nse"] < 0
    assert "not flood probability" in data["message"]


def _install_fake_local_model_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "REGIONAL_ML_PYTHON", Path(sys.executable))
    observation_file = tmp_path / "observations.csv"
    observation_file.write_text("station_id,state,observed_at,discharge_m3_s\\n", encoding="utf-8")
    monkeypatch.setattr(main, "REGIONAL_OBSERVATIONS", observation_file)
    model_file = tmp_path / "regional_discharge_lstm.pt"
    scaler_file = tmp_path / "regional_discharge_lstm.scalers.json"
    report_file = tmp_path / "regional_discharge_lstm.report.json"
    for path in (model_file, scaler_file, report_file):
        path.write_text("test", encoding="utf-8")
    monkeypatch.setattr(main, "REGIONAL_MODEL_FILE", model_file)
    monkeypatch.setattr(main, "REGIONAL_SCALERS_FILE", scaler_file)
    monkeypatch.setattr(main, "REGIONAL_REPORT_FILE", report_file)
    main._regional_inference_cache.clear()


def test_regional_inference_returns_503_until_local_assets_exist(monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    monkeypatch.setattr(main, "REGIONAL_ML_PYTHON", missing / "python")
    monkeypatch.setattr(main, "REGIONAL_OBSERVATIONS", missing / "observations.csv")
    monkeypatch.setattr(main, "REGIONAL_MODEL_FILE", missing / "model.pt")
    monkeypatch.setattr(main, "REGIONAL_SCALERS_FILE", missing / "scalers.json")
    monkeypatch.setattr(main, "REGIONAL_REPORT_FILE", missing / "report.json")
    response = client.get("/api/v1/models/regional-discharge/forecast")
    assert response.status_code == 503
    details = response.json()["detail"]
    assert "assets are not ready" in details["message"]
    assert details["asset_checks"]["model_weights"] is False
    assert any(step.endswith("bash deploy/ibm-linuxone/run-regional-lstm.sh train") for step in details["next_steps"])


def test_regional_inference_runs_saved_predictor_and_caches_result(monkeypatch, tmp_path):
    from types import SimpleNamespace

    _install_fake_local_model_assets(monkeypatch, tmp_path)
    calls = {"count": 0}

    def fake_run(command, **kwargs):
        calls["count"] += 1
        output_path = Path(command[command.index("--output-file") + 1])
        requested = next((arg.split("=", 1)[1] for arg in command if arg.startswith("--station-id=")), "TEST-STATION")
        payload = {
            "model_type": "validation_selected_lstm_persistence_blend",
            "status": "experimental_research_only",
            "station_id": requested,
            "state": "Karnataka",
            "forecast_origin_date": "2026-10-17",
            "history_window_end": "2026-10-17",
            "forecast_is_live": False,
            "history_freshness": "stale_historical_replay",
            "forecast": [
                {"date": "2026-10-18", "predicted_discharge_m3_s": 12.5,
                 "lstm_discharge_m3_s": 10.0, "persistence_baseline_discharge_m3_s": 15.0}
            ],
            "model_artifact": "/private/server/path/model.pt",
            "scalers_artifact": "/private/server/path/scalers.json",
        }
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = client.get(
        "/api/v1/models/regional-discharge/forecast",
        params={"station_id": "TEST-STATION"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "TEST-STATION"
    assert data["forecast"][0]["predicted_discharge_m3_s"] == 12.5
    assert data["serving_metadata"]["inference_mode"] == "on-demand saved-weight inference"
    assert data["serving_metadata"]["cache_hit"] is False
    assert "model_artifact" not in data and "scalers_artifact" not in data

    cached = client.get(
        "/api/v1/models/regional-discharge/forecast",
        params={"station_id": "TEST-STATION"},
    )
    assert cached.status_code == 200
    assert cached.json()["serving_metadata"]["cache_hit"] is True
    assert calls["count"] == 1


def test_regional_inference_rejects_invalid_station_id_and_negative_predictions(monkeypatch, tmp_path):
    from types import SimpleNamespace

    _install_fake_local_model_assets(monkeypatch, tmp_path)
    invalid_id = client.get("/api/v1/models/regional-discharge/forecast", params={"station_id": "--help"})
    assert invalid_id.status_code == 422

    def fake_run(command, **kwargs):
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text(json.dumps({
            "status": "experimental_research_only",
            "station_id": "TEST-STATION",
            "forecast": [{"predicted_discharge_m3_s": -2.0}],
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = client.get("/api/v1/models/regional-discharge/forecast")
    assert response.status_code == 502
    assert "negative discharge prediction" in response.json()["detail"]



def test_water_observations_are_paginated_and_labelled(monkeypatch):
    monkeypatch.setattr(main, "load_water_snapshot", lambda: {
        "generated_at_utc": "2026-10-18T00:00:00+00:00",
        "resource_count_checked": 37,
        "observations": [
            {
                "station_id": "A1", "station_name": "Gauge A", "state": "Telangana",
                "kind": "river_level", "value": 2.1, "unit": "m",
                "observed_at": "2026-10-17T00:00:00+00:00", "source_timezone": "UTC",
            },
            {
                "station_id": "B1", "station_name": "Gauge B", "state": "Kerala",
                "kind": "river_discharge", "value": 20.0, "unit": "m3/s",
                "observed_at": "2026-10-17T00:00:00", "source_timezone": "unknown",
            },
        ],
    })
    response = client.get("/api/v1/water-observations", params={"state": "Telangana", "limit": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 1
    assert data["observations"][0]["station_id"] == "A1"
    assert data["observations"][0]["freshness"] in {"recent", "delayed", "stale"}
    assert data["metadata"]["not_a_flood_warning"] is True


def test_water_observation_unknown_timezone_is_not_guessed(monkeypatch):
    monkeypatch.setattr(main, "load_water_snapshot", lambda: {
        "generated_at_utc": "2026-10-18T00:00:00+00:00",
        "observations": [{
            "station_id": "B1", "station_name": "Gauge B", "state": "Kerala",
            "kind": "river_level", "observed_at": "2026-10-17T00:00:00",
            "source_timezone": "unknown",
        }],
    })
    response = client.get("/api/v1/water-observations", params={"freshness": "unknown"})
    assert response.status_code == 200
    assert response.json()["observations"][0]["freshness"] == "unknown"
    assert response.json()["observations"][0]["age_hours"] is None


def test_water_observations_support_nearby_station_radius(monkeypatch):
    monkeypatch.setattr(main, "load_water_snapshot", lambda: {
        "generated_at_utc": "2026-10-18T00:00:00+00:00",
        "observations": [
            {
                "station_id": "NEAR", "station_name": "Nearby Gauge", "state": "Telangana",
                "kind": "river_level", "value": 2.1, "unit": "m",
                "latitude": 17.385, "longitude": 78.486,
                "observed_at": "2026-10-17T00:00:00+00:00", "source_timezone": "UTC",
            },
            {
                "station_id": "FAR", "station_name": "Far Gauge", "state": "Kerala",
                "kind": "river_level", "value": 3.1, "unit": "m",
                "latitude": 10.0, "longitude": 76.0,
                "observed_at": "2026-10-17T00:00:00+00:00", "source_timezone": "UTC",
            },
        ],
    })
    response = client.get(
        "/api/v1/water-observations",
        params={"latitude": 17.385, "longitude": 78.486, "radius_km": 25},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 1
    assert data["observations"][0]["station_id"] == "NEAR"
    assert data["observations"][0]["distance_km"] == 0.0


def test_water_nearby_filter_requires_both_coordinates():
    response = client.get("/api/v1/water-observations", params={"latitude": 17.385})
    assert response.status_code == 422


def test_river_flow_proxy_returns_model_metadata(monkeypatch):
    payload = {
        "latitude": 17.38,
        "longitude": 78.48,
        "timezone": "Asia/Kolkata",
        "daily": {
            "time": ["2026-10-18", "2026-10-19"],
            "river_discharge": [120.0, 135.0],
        },
    }
    monkeypatch.setattr(main, "urlopen", Mock(return_value=FakeResponse(payload)))
    response = client.get(
        "/api/v1/river-flow",
        params={"latitude": 17.38, "longitude": 78.48},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["daily"]["river_discharge"] == [120.0, 135.0]
    assert data["_floodwatch"]["provider"] == "Open-Meteo Flood API / GloFAS"
    assert "not a gauge observation" in data["_floodwatch"]["data_type"]
    main.urlopen.assert_called_once()


def test_river_flow_rejects_malformed_provider_series(monkeypatch):
    monkeypatch.setattr(main, "urlopen", Mock(return_value=FakeResponse({"daily": {"time": ["2026-10-18"]}})))
    response = client.get(
        "/api/v1/river-flow",
        params={"latitude": 17.38, "longitude": 78.48},
    )
    assert response.status_code == 502
    assert "valid daily discharge series" in response.json()["detail"]


def test_regional_inference_returns_station_aware_forecasts_for_map(monkeypatch, tmp_path):
    from types import SimpleNamespace

    _install_fake_local_model_assets(monkeypatch, tmp_path)
    calls = {"all_stations": False}

    def fake_run(command, **kwargs):
        calls["all_stations"] = "--all-stations" in command
        output_path = Path(command[command.index("--output-file") + 1])
        station = {
            "station_id": "TEST-STATION",
            "state": "Karnataka",
            "station_latitude": 15.0,
            "station_longitude": 76.0,
            "coordinates_available": True,
            "forecast_is_live": True,
            "history_age_days": 1,
            "peak_discharge_percentile_all_available_history": 91.0,
            "forecast": [{"date": "2026-10-20", "predicted_discharge_m3_s": 18.0}],
        }
        output_path.write_text(json.dumps({
            **station,
            "station_forecasts": [station],
            "forecast_station_count": 1,
            "model_type": "validation_selected_lstm_persistence_blend",
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = client.get(
        "/api/v1/models/regional-discharge/forecast",
        params={"all_stations": "true"},
    )

    assert response.status_code == 200
    data = response.json()
    assert calls["all_stations"] is True
    assert data["station_forecasts"][0]["station_id"] == "TEST-STATION"
    assert data["station_forecasts"][0]["peak_discharge_percentile_all_available_history"] == 91.0
    assert data["station_forecasts"][0]["coordinates_available"] is True
    assert data["serving_metadata"]["forecast_mode"] == "all_eligible_stations"
    assert data["serving_metadata"]["is_flood_probability"] is False


def test_regional_inference_rejects_all_stations_with_specific_station_id():
    response = client.get(
        "/api/v1/models/regional-discharge/forecast",
        params={"all_stations": "true", "station_id": "TEST-STATION"},
    )
    assert response.status_code == 422
    assert "not both" in response.json()["detail"]
