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


def test_model_status_does_not_claim_a_trained_forecast():
    response = client.get("/api/v1/models/status")
    assert response.status_code == 200
    data = response.json()
    assert data["validated_south_india_flood_forecast"] is False
    assert data["trained_model_artifact"] == "not_deployed"
    assert "verified historical discharge" in " ".join(data["required_before_inference"])


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
