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
