"""Current conditions and a short forecast for Ulaanbaatar from Open-Meteo."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from magic_town.errors import FetchError
from magic_town.http_json import get_json

SOURCE_NAME = "Open-Meteo"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ULAANBAATAR_LATITUDE = 47.92
ULAANBAATAR_LONGITUDE = 106.917
LOCAL_TZ = timezone(timedelta(hours=8))

# Labels for WMO weather interpretation codes used by Open-Meteo.
# Unknown codes stay numeric in the UI instead of receiving a guessed label.
WEATHER_LABELS = {
    0: ("Clear sky", "Цэлмэг"),
    1: ("Mainly clear", "Ерөнхийдөө цэлмэг"),
    2: ("Partly cloudy", "Багавтар үүлтэй"),
    3: ("Overcast", "Үүлэрхэг"),
    45: ("Fog", "Манан"),
    48: ("Depositing rime fog", "Хяруутай манан"),
    51: ("Light drizzle", "Сул шиврээ"),
    53: ("Moderate drizzle", "Дунд зэргийн шиврээ"),
    55: ("Dense drizzle", "Ширүүн шиврээ"),
    56: ("Light freezing drizzle", "Сул хөлдүү шиврээ"),
    57: ("Dense freezing drizzle", "Ширүүн хөлдүү шиврээ"),
    61: ("Slight rain", "Сул бороо"),
    63: ("Moderate rain", "Дунд зэргийн бороо"),
    65: ("Heavy rain", "Ширүүн бороо"),
    66: ("Light freezing rain", "Сул хөлдүү бороо"),
    67: ("Heavy freezing rain", "Ширүүн хөлдүү бороо"),
    71: ("Slight snow", "Сул цас"),
    73: ("Moderate snow", "Дунд зэргийн цас"),
    75: ("Heavy snow", "Ширүүн цас"),
    77: ("Snow grains", "Цасан ширхэг"),
    80: ("Slight rain showers", "Сул аадар бороо"),
    81: ("Moderate rain showers", "Дунд зэргийн аадар бороо"),
    82: ("Violent rain showers", "Ширүүн аадар бороо"),
    85: ("Slight snow showers", "Сул цасан шуурга"),
    86: ("Heavy snow showers", "Ширүүн цасан шуурга"),
    95: ("Thunderstorm", "Аянга цахилгаан"),
    96: ("Thunderstorm with slight hail", "Бага мөндөртэй аянга"),
    99: ("Thunderstorm with heavy hail", "Ширүүн мөндөртэй аянга"),
}


def weather_label(code: int, lang: str) -> str:
    pair = WEATHER_LABELS.get(code)
    if pair is None:
        return f"Code {code}" if lang == "en" else f"Код {code}"
    return pair[0] if lang == "en" else pair[1]


def compass_point(degrees: float) -> str:
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[round(degrees / 45) % 8]


def fetch_weather() -> dict:
    params = {
        "latitude": ULAANBAATAR_LATITUDE,
        "longitude": ULAANBAATAR_LONGITUDE,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
            ]
        ),
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "sunrise",
                "sunset",
            ]
        ),
        "timezone": "Asia/Ulaanbaatar",
        "forecast_days": 3,
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
    }
    body, final_url = get_json(FORECAST_URL, params)
    payload = _normalize(body)
    validate_weather_payload(payload)
    fetched_at = datetime.now(LOCAL_TZ).replace(microsecond=0)
    return {
        "fetched_at": fetched_at.isoformat(),
        "fetched_at_epoch": time.time(),
        "source_name": SOURCE_NAME,
        "source_url": final_url,
        "payload": payload,
    }


def validate_weather_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise FetchError("shape", "weather payload is not an object")
    current = payload.get("current")
    daily = payload.get("daily")
    if not isinstance(current, dict) or not isinstance(current.get("time"), str):
        raise FetchError("shape", "Open-Meteo current.time is missing")
    _number(current.get("temperature_c"), "temperature_c", required=True)
    _integer(current.get("weather_code"), "weather_code", required=True)
    if not isinstance(daily, list) or not daily:
        raise FetchError("shape", "Open-Meteo daily forecast is missing")
    for index, day in enumerate(daily):
        if not isinstance(day, dict) or not isinstance(day.get("date"), str):
            raise FetchError("shape", f"daily[{index}] has no date")
        _number(day.get("temp_max"), f"daily[{index}].temp_max", required=True)
        _number(day.get("temp_min"), f"daily[{index}].temp_min", required=True)
        _integer(day.get("weather_code"), f"daily[{index}].weather_code", required=True)


def _normalize(body: dict) -> dict:
    current = body.get("current")
    daily = body.get("daily")
    current_units = body.get("current_units") if isinstance(body.get("current_units"), dict) else {}
    daily_units = body.get("daily_units") if isinstance(body.get("daily_units"), dict) else {}
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise FetchError("shape", "Open-Meteo current or daily block is missing")

    dates = daily.get("time")
    if not isinstance(dates, list) or not dates:
        raise FetchError("shape", "Open-Meteo daily.time is missing")

    days = []
    for index, date in enumerate(dates):
        days.append(
            {
                "date": date,
                "weather_code": _at(daily, "weather_code", index, integer=True),
                "temp_min": _at(daily, "temperature_2m_min", index),
                "temp_max": _at(daily, "temperature_2m_max", index),
                "precip_sum": _at(daily, "precipitation_sum", index),
                "precip_probability": _at(daily, "precipitation_probability_max", index),
                "sunrise": _at(daily, "sunrise", index, text=True),
                "sunset": _at(daily, "sunset", index, text=True),
            }
        )

    latitude = body.get("latitude")
    longitude = body.get("longitude")
    return {
        "latitude": latitude if isinstance(latitude, (int, float)) else ULAANBAATAR_LATITUDE,
        "longitude": longitude if isinstance(longitude, (int, float)) else ULAANBAATAR_LONGITUDE,
        "timezone": body.get("timezone") if isinstance(body.get("timezone"), str) else "Asia/Ulaanbaatar",
        "elevation_m": body.get("elevation") if isinstance(body.get("elevation"), (int, float)) else None,
        "units": {
            "temperature": _unit(current_units, "temperature_2m", "°C"),
            "apparent_temperature": _unit(current_units, "apparent_temperature", "°C"),
            "humidity": _unit(current_units, "relative_humidity_2m", "%"),
            "precipitation": _unit(current_units, "precipitation", "mm"),
            "cloud": _unit(current_units, "cloud_cover", "%"),
            "wind_speed": _unit(current_units, "wind_speed_10m", "m/s"),
            "daily_temperature": _unit(daily_units, "temperature_2m_max", "°C"),
            "daily_precipitation": _unit(daily_units, "precipitation_sum", "mm"),
            "daily_probability": _unit(daily_units, "precipitation_probability_max", "%"),
        },
        "current": {
            "time": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "apparent_c": current.get("apparent_temperature"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "precipitation_mm": current.get("precipitation"),
            "weather_code": current.get("weather_code"),
            "cloud_pct": current.get("cloud_cover"),
            "wind_speed": current.get("wind_speed_10m"),
            "wind_direction_deg": current.get("wind_direction_10m"),
        },
        "daily": days,
    }


def _unit(units: dict, key: str, fallback: str) -> str:
    value = units.get(key)
    return value if isinstance(value, str) and value else fallback


def _at(block: dict, key: str, index: int, integer: bool = False, text: bool = False):
    values = block.get(key)
    if not isinstance(values, list) or index >= len(values):
        raise FetchError("shape", f"daily.{key} is shorter than daily.time")
    value = values[index]
    if text:
        return value if isinstance(value, str) else None
    if integer:
        return _integer(value, f"daily.{key}[{index}]", required=True)
    return _number(value, f"daily.{key}[{index}]", required=False)


def _number(value, field: str, required: bool):
    if value is None:
        if required:
            raise FetchError("shape", f"{field} is missing")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FetchError("shape", f"{field} is not a number")
    return float(value)


def _integer(value, field: str, required: bool):
    if value is None:
        if required:
            raise FetchError("shape", f"{field} is missing")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FetchError("shape", f"{field} is not an integer")
    return int(value)
