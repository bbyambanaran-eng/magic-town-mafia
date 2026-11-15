"""Historical Ulaanbaatar weather data and transparent summaries."""

from __future__ import annotations

from calendar import isleap, monthrange

import pandas as pd
import requests
import streamlit as st

WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"

LATITUDE = 47.92
LONGITUDE = 106.917
START_YEAR = 1991
END_YEAR = 2025
BASELINE_START = 1991
BASELINE_END = 2020
START_DATE = "1990-12-01"  # December completes the first DJF season (1991).
END_DATE = f"{END_YEAR}-12-31"

SEASON_MONTHS = {
    "Winter (DJF)": (12, 1, 2),
    "Spring (MAM)": (3, 4, 5),
    "Summer (JJA)": (6, 7, 8),
    "Autumn (SON)": (9, 10, 11),
}


@st.cache_data(ttl=3600, show_spinner=False)
def load_historical_weather() -> pd.DataFrame:
    """Fetch and clean daily ERA5 data; preserve missing measurements as null."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "Asia/Ulaanbaatar",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "models": "era5",
    }

    response = requests.get(
        WEATHER_URL,
        params=params,
        timeout=30,
        headers={"User-Agent": "MagicTown/0.1 (educational weather analysis)"},
    )
    response.raise_for_status()
    payload = response.json()
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, dict):
        raise ValueError("Open-Meteo response did not include a daily data object")

    dates = daily.get("time")
    temperatures = daily.get("temperature_2m_mean")
    precipitation = daily.get("precipitation_sum")
    if not all(isinstance(values, list) for values in (dates, temperatures, precipitation)):
        raise ValueError("Open-Meteo daily response is missing a requested variable")
    if not (len(dates) == len(temperatures) == len(precipitation)):
        raise ValueError("Open-Meteo daily variables do not align by date")

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(dates, errors="coerce"),
            "temperature_c": pd.to_numeric(temperatures, errors="coerce"),
            "precipitation_mm": pd.to_numeric(precipitation, errors="coerce"),
        }
    )

    # Discard unusable dates and duplicate days, but keep a day if either
    # requested measurement is present so coverage remains variable-specific.
    frame = frame.dropna(subset=["date"])
    frame = frame.drop_duplicates(subset=["date"], keep="first")
    frame = frame.dropna(subset=["temperature_c", "precipitation_mm"], how="all")
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    return frame


def summarize_annual_weather(weather: pd.DataFrame) -> pd.DataFrame:
    """Aggregate yearly means/totals and report valid-day coverage."""
    frame = _analysis_period(weather)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "year", "mean_temperature", "total_precipitation",
                "temperature_days", "precipitation_days", "expected_days",
                "temperature_coverage_pct", "precipitation_coverage_pct",
            ]
        )

    summary = frame.groupby("year", as_index=False).agg(
        mean_temperature=("temperature_c", "mean"),
        total_precipitation=("precipitation_mm", lambda values: values.sum(min_count=1)),
        temperature_days=("temperature_c", "count"),
        precipitation_days=("precipitation_mm", "count"),
    )
    summary["expected_days"] = summary["year"].map(
        lambda year: 366 if isleap(int(year)) else 365
    )
    summary["temperature_coverage_pct"] = (
        summary["temperature_days"] / summary["expected_days"] * 100
    ).clip(upper=100)
    summary["precipitation_coverage_pct"] = (
        summary["precipitation_days"] / summary["expected_days"] * 100
    ).clip(upper=100)
    return summary


def summarize_seasonal_weather(weather: pd.DataFrame) -> pd.DataFrame:
    """Aggregate meteorological seasons; December belongs to the next winter."""
    if weather.empty:
        return pd.DataFrame(
            columns=[
                "year", "season", "mean_temperature", "total_precipitation",
                "temperature_days", "precipitation_days", "expected_days",
                "temperature_coverage_pct", "precipitation_coverage_pct",
            ]
        )

    # Keep December before the first displayed year so the first DJF season is
    # complete; no earlier date enters the annual summaries.
    frame = weather.copy()
    included_dates = frame["year"].between(START_YEAR, END_YEAR) | (
        frame["year"].eq(START_YEAR - 1) & frame["month"].eq(12)
    )
    frame = frame[included_dates]
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "year", "season", "mean_temperature", "total_precipitation",
                "temperature_days", "precipitation_days", "expected_days",
                "temperature_coverage_pct", "precipitation_coverage_pct",
            ]
        )

    month_to_season = {
        month: season
        for season, months in SEASON_MONTHS.items()
        for month in months
    }
    frame["season"] = frame["month"].map(month_to_season)
    frame["season_year"] = frame["year"] + frame["month"].eq(12).astype(int)
    frame = frame[frame["season_year"].between(START_YEAR, END_YEAR)]
    summary = frame.groupby(["season_year", "season"], as_index=False).agg(
        mean_temperature=("temperature_c", "mean"),
        total_precipitation=("precipitation_mm", lambda values: values.sum(min_count=1)),
        temperature_days=("temperature_c", "count"),
        precipitation_days=("precipitation_mm", "count"),
    )
    summary = summary.rename(columns={"season_year": "year"})
    summary["expected_days"] = summary.apply(
        lambda row: _expected_season_days(int(row["year"]), str(row["season"])),
        axis=1,
    )
    summary["temperature_coverage_pct"] = (
        summary["temperature_days"] / summary["expected_days"] * 100
    ).clip(upper=100)
    summary["precipitation_coverage_pct"] = (
        summary["precipitation_days"] / summary["expected_days"] * 100
    ).clip(upper=100)
    return summary


def _analysis_period(weather: pd.DataFrame) -> pd.DataFrame:
    if weather.empty:
        return weather.copy()
    return weather[
        weather["year"].between(START_YEAR, END_YEAR)
    ].copy()


def _expected_season_days(year: int, season: str) -> int:
    total = 0
    for month in SEASON_MONTHS[season]:
        month_year = year - 1 if season == "Winter (DJF)" and month == 12 else year
        total += monthrange(month_year, month)[1]
    return total
