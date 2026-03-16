"""Weather data fetcher using Open-Meteo (free, no API key required).

Usage::

    from flipdisc.services.weather import fetch_weather

    data = await fetch_weather(37.77, -122.41, unit="F")
    print(data.temp, data.condition)  # e.g. 72.3, "sunny"
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

# WMO weather interpretation codes → canonical condition strings
# https://open-meteo.com/en/docs#weathervariables
WMO_TO_CONDITION: dict[int, str] = {
    0: "sunny",
    1: "partly_cloudy",
    2: "partly_cloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "rain",
    53: "rain",
    55: "rain",
    56: "rain",
    57: "rain",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "rain",
    67: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class WeatherData:
    temp: float
    condition: str  # one of the canonical condition strings
    unit: str  # "F" or "C"


async def fetch_weather(
    latitude: float,
    longitude: float,
    unit: str = "F",
    timeout: float = 10.0,
) -> WeatherData:
    """Fetch current weather from Open-Meteo.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.
        unit: Temperature unit — "F" (Fahrenheit) or "C" (Celsius).
        timeout: Request timeout in seconds.

    Returns:
        WeatherData with temp, condition, and unit.

    Raises:
        httpx.HTTPError: On network or HTTP failure.
        KeyError: If the API response is missing expected fields.
    """
    temp_unit_param = "fahrenheit" if unit.upper() == "F" else "celsius"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": "true",
        "temperature_unit": temp_unit_param,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(_OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()

    current = data["current_weather"]
    temp = float(current["temperature"])
    wmo_code = int(current["weathercode"])
    is_day = int(current.get("is_day", 1))
    condition = WMO_TO_CONDITION.get(wmo_code, "cloudy")

    # Use moon icon for clear-sky night (WMO 0 at night)
    if wmo_code == 0 and is_day == 0:
        condition = "moon"

    return WeatherData(temp=temp, condition=condition, unit=unit.upper())
