"""Magic Town data screen and Mafia game lobby.

Run from the repository root:

    streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from magic_town.analysis import load_historical_weather, load_plant_occurrences
from magic_town.cache_store import LoadResult, load_live
from magic_town.game_lobby import render_game_lobby
from magic_town.i18n import error_text, tr
from magic_town.plants import basis_label, fetch_plants, validate_plants_payload
from magic_town.weather import (
    compass_point,
    fetch_weather,
    validate_weather_payload,
    weather_label,
)

TTL_SECONDS = 600
RETRY_SECONDS = 60


def main() -> None:
    st.set_page_config(page_title="Magic Town", layout="wide")
    lang, force = _sidebar()
    _header(lang)

    weather_tab, plants_tab, analysis_tab, mafia_tab = st.tabs(
        [
            tr(lang, "tab_weather"),
            tr(lang, "tab_plants"),
            "Дата анализ" if lang == "mn" else "Data analysis",
            "🎭 Mafia",
        ]
    )

    with weather_tab:
        _render_section(
            lang,
            "weather",
            tr(lang, "loading_weather"),
            _render_weather,
            force,
        )

    with plants_tab:
        _render_section(
            lang,
            "plants",
            tr(lang, "loading_plants"),
            _render_plants,
            force,
        )

    with analysis_tab:
        _render_analysis(lang, force)

    with mafia_tab:
        render_game_lobby(lang)


def _sidebar() -> tuple[str, bool]:
    if "lang" not in st.session_state:
        st.session_state["lang"] = "mn"

    with st.sidebar:
        st.header("Magic Town")
        choice = st.radio(
            tr(st.session_state["lang"], "language"),
            options=["mn", "en"],
            format_func=lambda code: "Монгол" if code == "mn" else "English",
            key="lang",
        )
        lang = choice if choice in ("mn", "en") else "mn"
        st.write(tr(lang, "about"))
        force = st.button(tr(lang, "refresh"), width="stretch")
        st.caption(tr(lang, "next_step"))

    return lang, force


def _header(lang: str) -> None:
    st.title("Magic Town")
    st.write(tr(lang, "tagline"))


def _render_section(lang: str, name: str, spinner: str, renderer, force: bool) -> None:
    try:
        with st.spinner(spinner):
            if name == "weather":
                result = load_live(
                    name,
                    fetch_weather,
                    validate_weather_payload,
                    force=force,
                    ttl_seconds=TTL_SECONDS,
                    retry_seconds=RETRY_SECONDS,
                )
            else:
                result = load_live(
                    name,
                    fetch_plants,
                    validate_plants_payload,
                    force=force,
                    ttl_seconds=TTL_SECONDS,
                    retry_seconds=RETRY_SECONDS,
                )

        if not result.ok or result.record is None:
            _render_failure(lang, result)
            return

        _render_status(lang, result)
        renderer(lang, result.record["payload"])
        _render_provenance(lang, result.record)

    except Exception as exc:
        st.error(tr(lang, "section_down"))
        with st.expander(tr(lang, "technical")):
            st.code(f"{type(exc).__name__}: {exc}")


def _render_failure(lang: str, result: LoadResult) -> None:
    reason = error_text(lang, result.error_code)
    st.error(tr(lang, "no_data"))
    st.write(reason)

    if result.retry_in_seconds is not None:
        st.caption(tr(lang, "retry_hint", wait=result.retry_in_seconds))

    if result.error_detail:
        with st.expander(tr(lang, "technical")):
            st.code(result.error_detail)


def _render_status(lang: str, result: LoadResult) -> None:
    record = result.record or {}

    if result.state == "fetched":
        st.success(tr(lang, "state_fetched"))
        return

    if result.state == "cached":
        minutes, seconds = divmod(result.refresh_in_seconds or 0, 60)
        st.info(tr(lang, "state_cached", minutes=minutes, seconds=seconds))
        return

    if result.state == "stale":
        st.warning(
            tr(
                lang,
                "state_stale",
                reason=error_text(lang, result.error_code),
                time=record.get("fetched_at", "—"),
                wait=result.retry_in_seconds or 0,
            )
        )
        if result.error_detail:
            with st.expander(tr(lang, "technical")):
                st.code(result.error_detail)


def _render_provenance(lang: str, record: dict) -> None:
    st.divider()
    st.write(f"{tr(lang, 'source')}: {record.get('source_name', '—')}")
    st.write(f"{tr(lang, 'fetched_at')}: {record.get('fetched_at', '—')}")

    source_url = str(record.get("source_url", ""))
    if source_url.startswith("https://"):
        st.link_button(tr(lang, "request_url"), source_url)


def _render_weather(lang: str, payload: dict) -> None:
    units = payload["units"]
    current = payload["current"]

    st.subheader(tr(lang, "weather_title"))
    st.caption(
        tr(
            lang,
            "weather_point",
            lat=float(payload["latitude"]),
            lon=float(payload["longitude"]),
            timezone=payload["timezone"],
        )
    )

    if payload.get("elevation_m") is not None:
        st.caption(tr(lang, "elevation", value=round(float(payload["elevation_m"]))))

    code = int(current["weather_code"])
    st.write(f"**{tr(lang, 'condition')}:** {weather_label(code, lang)} ({code})")
    st.caption(f"**{tr(lang, 'model_time')}:** {current['time']} ({payload['timezone']})")

    wind = _measure(current.get("wind_speed"), units["wind_speed"], 1)
    direction = current.get("wind_direction_deg")
    if isinstance(direction, (int, float)) and not isinstance(direction, bool):
        wind = f"{wind} · {float(direction):.0f}° ({compass_point(float(direction))})"

    first, second, third = st.columns(3)
    first.metric(
        tr(lang, "temperature"),
        _measure(current.get("temperature_c"), units["temperature"], 1),
    )
    second.metric(
        tr(lang, "feels_like"),
        _measure(current.get("apparent_c"), units["apparent_temperature"], 1),
    )
    third.metric(
        tr(lang, "humidity"),
        _measure(current.get("humidity_pct"), units["humidity"], 0),
    )

    first, second, third = st.columns(3)
    first.metric(
        tr(lang, "precip"),
        _measure(current.get("precipitation_mm"), units["precipitation"], 1),
    )
    second.metric(tr(lang, "wind"), wind)
    third.metric(
        tr(lang, "cloud"),
        _measure(current.get("cloud_pct"), units["cloud"], 0),
    )

    st.subheader(tr(lang, "forecast"))
    rows = []

    for day in payload["daily"]:
        rows.append(
            {
                tr(lang, "col_date"): day["date"],
                tr(lang, "col_condition"): weather_label(
                    int(day["weather_code"]), lang
                ),
                tr(lang, "col_low"): _measure(
                    day.get("temp_min"), units["daily_temperature"], 1
                ),
                tr(lang, "col_high"): _measure(
                    day.get("temp_max"), units["daily_temperature"], 1
                ),
                tr(lang, "col_precip"): _measure(
                    day.get("precip_sum"), units["daily_precipitation"], 1
                ),
                tr(lang, "col_chance"): _measure(
                    day.get("precip_probability"), units["daily_probability"], 0
                ),
                tr(lang, "col_sunrise"): day.get("sunrise") or "—",
                tr(lang, "col_sunset"): day.get("sunset") or "—",
            }
        )

    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _render_plants(lang: str, payload: dict) -> None:
    st.subheader(tr(lang, "plants_title"))
    st.write(
        tr(
            lang,
            "plants_query",
            total=int(payload["total_count"]),
            returned=int(payload["returned"]),
        )
    )

    records = payload["records"]
    if not records:
        st.info(tr(lang, "plants_empty"))
        return

    rows = []
    map_rows = []

    for record in records:
        link = record.get("occurrence_url") or ""
        rows.append(
            {
                tr(lang, "col_name"): record.get("scientific_name") or "—",
                tr(lang, "col_common"): record.get("vernacular_name") or "—",
                tr(lang, "col_family"): record.get("family") or "—",
                tr(lang, "col_region"): record.get("state_province") or "—",
                tr(lang, "col_locality"): record.get("locality") or "—",
                tr(lang, "col_observed"): record.get("event_date") or "—",
                tr(lang, "col_basis"): basis_label(
                    record.get("basis_of_record"), lang
                ),
                tr(lang, "col_dataset"): record.get("dataset_name") or "—",
                tr(lang, "col_recorder"): record.get("recorded_by") or "—",
                tr(lang, "col_link"): link,
            }
        )

        if record.get("latitude") is not None and record.get("longitude") is not None:
            map_rows.append(
                {
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "name": record.get("scientific_name")
                    or record.get("gbif_id")
                    or "",
                }
            )

    link_column = tr(lang, "col_link")
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            link_column: st.column_config.LinkColumn(
                link_column,
                display_text="GBIF",
            ),
        },
    )

    if map_rows:
        st.caption(tr(lang, "map_caption", count=len(map_rows)))
        st.map(
            pd.DataFrame(map_rows),
            latitude="latitude",
            longitude="longitude",
        )
    else:
        st.caption(tr(lang, "no_coords"))


def _render_analysis(lang: str, force: bool) -> None:
    if force:
        load_historical_weather.clear()
        load_plant_occurrences.clear()

    st.subheader(
        "Түүхэн дата анализ" if lang == "mn" else "Historical data analysis"
    )

    try:
        weather_df = load_historical_weather()

        if weather_df.empty:
            st.warning(
                "Цаг агаарын түүхэн дата олдсонгүй."
                if lang == "mn"
                else "No historical weather data found."
            )
        else:
            yearly_weather = (
                weather_df.groupby("year", as_index=False)
                .agg(
                    mean_temperature=("temperature_c", "mean"),
                    total_precipitation=("precipitation_mm", "sum"),
                )
            )

            st.caption(
                f"Open-Meteo · 2020–2025 · {len(weather_df):,} өдөр"
                if lang == "mn"
                else f"Open-Meteo · 2020–2025 · {len(weather_df):,} daily records"
            )

            temperature_chart = px.line(
                yearly_weather,
                x="year",
                y="mean_temperature",
                markers=True,
                title=(
                    "Жилийн дундаж температур"
                    if lang == "mn"
                    else "Annual mean temperature"
                ),
                labels={
                    "year": "Жил" if lang == "mn" else "Year",
                    "mean_temperature": (
                        "Температур °C" if lang == "mn" else "Temperature °C"
                    ),
                },
            )
            st.plotly_chart(temperature_chart, width="stretch")

            rain_chart = px.bar(
                yearly_weather,
                x="year",
                y="total_precipitation",
                title=(
                    "Жилийн хур тунадас"
                    if lang == "mn"
                    else "Annual precipitation"
                ),
                labels={
                    "year": "Жил" if lang == "mn" else "Year",
                    "total_precipitation": (
                        "Хур тунадас, мм"
                        if lang == "mn"
                        else "Precipitation, mm"
                    ),
                },
            )
            st.plotly_chart(rain_chart, width="stretch")

    except Exception as exc:
        st.error(
            "Цаг агаарын түүхэн дата татаж чадсангүй."
            if lang == "mn"
            else "Could not fetch historical weather data."
        )
        with st.expander(tr(lang, "technical")):
            st.code(f"{type(exc).__name__}: {exc}")

    st.divider()

    try:
        plants_df, total_count, cleaned_count = load_plant_occurrences()

        st.caption(
            f"GBIF · Монгол · 2020–2025 · түүвэрт {cleaned_count:,} цэвэр бүртгэл"
            if lang == "mn"
            else (
                f"GBIF · Mongolia · 2020–2025 · "
                f"{cleaned_count:,} cleaned sample records"
            )
        )

        if plants_df.empty:
            st.info(
                "Цэвэрлэсний дараа ургамлын бүртгэл үлдсэнгүй."
                if lang == "mn"
                else "No plant records remained after cleaning."
            )
        else:
            yearly_plants = (
                plants_df.groupby("year")
                .size()
                .reset_index(name="records")
            )

            plant_chart = px.bar(
                yearly_plants,
                x="year",
                y="records",
                title=(
                    "GBIF-д бүртгэгдсэн ажиглалт жилээр"
                    if lang == "mn"
                    else "GBIF occurrences by year"
                ),
                labels={
                    "year": "Жил" if lang == "mn" else "Year",
                    "records": (
                        "Бүртгэлийн тоо"
                        if lang == "mn"
                        else "Occurrence records"
                    ),
                },
            )
            st.plotly_chart(plant_chart, width="stretch")

            top_species = (
                plants_df.groupby("scientific_name")
                .size()
                .nlargest(10)
                .sort_values()
                .reset_index(name="records")
            )

            species_chart = px.bar(
                top_species,
                x="records",
                y="scientific_name",
                orientation="h",
                title=(
                    "Түүвэрт хамгийн олон бүртгэгдсэн зүйлс"
                    if lang == "mn"
                    else "Most recorded species in the sample"
                ),
                labels={
                    "scientific_name": (
                        "Шинжлэх ухааны нэр"
                        if lang == "mn"
                        else "Scientific name"
                    ),
                    "records": (
                        "Ажиглалтын бүртгэл"
                        if lang == "mn"
                        else "Occurrence records"
                    ),
                },
            )
            st.plotly_chart(species_chart, width="stretch")

        st.caption(
            "Дутуу жил/нэртэй болон давхардсан мөрийг цэвэрлэсэн. "
            "GBIF бүртгэлийн тоо нь ургамлын бодит тоо толгой биш."
            if lang == "mn"
            else (
                "Rows missing year or name and duplicate records were removed. "
                "GBIF record counts are not plant population sizes."
            )
        )

        st.caption(
            f"GBIF-ийн таарсан нийт бүртгэл: {total_count:,}. "
            f"Анализад ашигласан цэвэр түүвэр: {cleaned_count:,}."
            if lang == "mn"
            else (
                f"Total matching GBIF records: {total_count:,}. "
                f"Clean sample used for analysis: {cleaned_count:,}."
            )
        )

    except Exception as exc:
        st.error(
            "GBIF анализын дата татаж чадсангүй."
            if lang == "mn"
            else "Could not fetch GBIF analysis data."
        )
        with st.expander(tr(lang, "technical")):
            st.code(f"{type(exc).__name__}: {exc}")

    st.caption(
        "Эх сурвалж: Open-Meteo Historical Weather API · GBIF Occurrence API"
        if lang == "mn"
        else "Sources: Open-Meteo Historical Weather API · GBIF Occurrence API"
    )


def _measure(value, unit: str, digits: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{float(value):.{digits}f} {unit}".strip()


if __name__ == "__main__":
    main()