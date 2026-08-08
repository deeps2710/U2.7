from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class WeatherSnapshot:
    location: str
    region: str
    country: str
    latitude: float
    longitude: float
    temperature_c: float
    apparent_temperature_c: float
    humidity_percent: int
    wind_speed_kmh: float
    weather_code: int
    condition: str
    observed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_current_weather(location: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> WeatherSnapshot:
    query = " ".join(str(location or "").strip().split())
    if not query:
        raise ValueError("A location is required for the weather briefing.")

    place = _get_json(
        GEOCODING_ENDPOINT,
        {"name": query, "count": 1, "language": "en", "format": "json"},
        timeout=timeout,
    )
    results = place.get("results") if isinstance(place, dict) else None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise LookupError(f"Could not find weather coordinates for {query}.")

    resolved = results[0]
    latitude = float(resolved["latitude"])
    longitude = float(resolved["longitude"])
    forecast = _get_json(
        FORECAST_ENDPOINT,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        },
        timeout=timeout,
    )
    current = forecast.get("current") if isinstance(forecast, dict) else None
    if not isinstance(current, dict):
        raise LookupError(f"Weather conditions are unavailable for {query}.")

    code = int(current.get("weather_code", -1))
    return WeatherSnapshot(
        location=str(resolved.get("name") or query),
        region=str(resolved.get("admin1") or ""),
        country=str(resolved.get("country") or ""),
        latitude=latitude,
        longitude=longitude,
        temperature_c=float(current["temperature_2m"]),
        apparent_temperature_c=float(current.get("apparent_temperature", current["temperature_2m"])),
        humidity_percent=int(current.get("relative_humidity_2m", 0)),
        wind_speed_kmh=float(current.get("wind_speed_10m", 0.0)),
        weather_code=code,
        condition=weather_code_description(code),
        observed_at=str(current.get("time") or ""),
    )


def weather_code_description(code: int) -> str:
    if code == 0:
        return "clear"
    if code in {1, 2}:
        return "partly cloudy"
    if code == 3:
        return "overcast"
    if code in {45, 48}:
        return "foggy"
    if code in {51, 53, 55, 56, 57}:
        return "drizzly"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "rainy"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snowy"
    if code in {95, 96, 99}:
        return "stormy"
    return "mixed conditions"


def _get_json(endpoint: str, params: dict[str, object], *, timeout: float) -> dict[str, Any]:
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "ULTRON/2.7 local assistant"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("Weather provider returned an invalid response.")
    return payload
