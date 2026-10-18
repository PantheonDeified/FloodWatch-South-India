"""FloodWatch South India API.

A small public-data API for the FloodWatch browser frontend.
This service proxies Open-Meteo weather for South India and labels model data
as estimates. It does not calculate or issue flood warnings.
"""
from datetime import datetime, timezone
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

APP_VERSION = "0.2.0"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

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
        "water_observations": "Published GitHub Pages JSON snapshot; collector runs every six hours when scheduled execution succeeds; observation freshness varies by source",
        "flood_forecast_model": "Not yet deployed or locally validated",
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


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
