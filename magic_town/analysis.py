"""Historical weather and plant occurrence data for analysis."""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
GBIF_URL = "https://api.gbif.org/v1/occurrence/search"

LATITUDE = 47.92
LONGITUDE = 106.917
START_DATE = "2020-01-01"
END_DATE = "2025-12-31"

PAGE_SIZE = 300
MAX_GBIF_RECORDS = 3000


@st.cache_data(ttl=3600, show_spinner=False)
def load_historical_weather() -> pd.DataFrame:
    """Fetch and clean Ulaanbaatar daily historical weather."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "Asia/Ulaanbaatar",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }

    response = requests.get(
        WEATHER_URL,
        params=params,
        timeout=30,
        headers={"User-Agent": "MagicTown/0.1"},
    )
    response.raise_for_status()
    daily = response.json().get("daily", {})

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(daily.get("time", []), errors="coerce"),
            "temperature_c": pd.to_numeric(
                daily.get("temperature_2m_mean", []), errors="coerce"
            ),
            "precipitation_mm": pd.to_numeric(
                daily.get("precipitation_sum", []), errors="coerce"
            ),
        }
    )

    # Remove invalid rows, then derive fields used for aggregation.
    frame = frame.dropna(subset=["date"]).drop_duplicates(subset=["date"])
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    return frame


@st.cache_data(ttl=3600, show_spinner=False)
def load_plant_occurrences() -> tuple[pd.DataFrame, int, int]:
    """Fetch a bounded GBIF sample and clean its occurrence records."""
    params = {
        "country": "MN",
        "kingdomKey": 6,
        "year": "2020,2025",
        "hasCoordinate": "true",
        "limit": PAGE_SIZE,
        "offset": 0,
    }

    first_response = requests.get(
        GBIF_URL,
        params=params,
        timeout=30,
        headers={"User-Agent": "MagicTown/0.1"},
    )
    first_response.raise_for_status()
    first_page = first_response.json()

    total_count = int(first_page.get("count", 0))
    records: list[dict] = []
    fetch_count = min(total_count, MAX_GBIF_RECORDS)

    for offset in range(0, fetch_count, PAGE_SIZE):
        page_params = {**params, "offset": offset}
        response = requests.get(
            GBIF_URL,
            params=page_params,
            timeout=30,
            headers={"User-Agent": "MagicTown/0.1"},
        )
        response.raise_for_status()
        records.extend(response.json().get("results", []))

    frame = pd.DataFrame(
        [
            {
                "gbif_id": str(row.get("gbifID") or ""),
                "scientific_name": str(row.get("scientificName") or "").strip(),
                "year": row.get("year"),
                "family": str(row.get("family") or "").strip(),
                "region": str(row.get("stateProvince") or "").strip(),
            }
            for row in records
        ]
    )

    if frame.empty:
        return frame, total_count, 0

    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame = frame.dropna(subset=["year", "scientific_name"])
    frame = frame[frame["scientific_name"] != ""]
    frame = frame[frame["year"].between(2020, 2025)]
    frame["year"] = frame["year"].astype(int)

    # GBIF rows are occurrence records; deduplicate by their record ID.
    frame = frame[frame["gbif_id"] != ""]
    frame = frame.drop_duplicates(subset=["gbif_id"])

    return frame, total_count, len(frame)