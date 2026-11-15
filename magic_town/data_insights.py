"""Live conditions and transparent historical weather analysis."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from .analysis import (
    BASELINE_END,
    BASELINE_START,
    LATITUDE,
    LONGITUDE,
    load_historical_weather,
    summarize_annual_weather,
    summarize_seasonal_weather,
)
from .weather import fetch_weather, weather_label

SEASONS = (
    "Winter (DJF)",
    "Spring (MAM)",
    "Summer (JJA)",
    "Autumn (SON)",
)


def render_data_insights(lang: str = "en") -> None:
    """Render the English-language data page, independent from the game screen."""
    st.title("Ulaanbaatar weather")
    st.write(
        "**Research question:** How have daily temperature and precipitation in Ulaanbaatar varied by year and season since 1991?"
    )
    st.caption(
        "The Game page uses live Ulaanbaatar weather for its atmosphere. This page puts that setting in context: today's forecast is compared with historical records, then annual and seasonal patterns are explored. Weather does not change roles, votes, or game outcomes."
    )

    with st.expander("Data sources, processing, and limitations"):
        st.markdown(
            "- **Live conditions:** Open-Meteo Forecast API at one Ulaanbaatar coordinate (47.92, 106.917), refreshed every 15 minutes. The daily forecast is compared with the ERA5 average daily value for that calendar month in 1991–2020."
            "\n- **Historical analysis:** Open-Meteo Historical Weather API, ERA5 reanalysis, daily mean 2 m temperature and total precipitation, 1991–2025. December 1990 is included only to complete winter 1991 (December–February)."
            "\n- **Processing:** Invalid dates and duplicate dates are removed. Missing values remain missing. Annual and meteorological-season summaries report variable-specific valid-day coverage; precipitation is never filled with zero."
            "\n- **Limitations:** The forecast and ERA5 are different weather products. ERA5 is a model-based reanalysis on an approximately 25 km grid, not a thermometer at the displayed coordinate. The live-to-history comparison is descriptive, not a direct station measurement. This single point represents Ulaanbaatar only; historical differences do not establish a cause or a long-term climate trend."
        )

    if st.button("Refresh data", icon=":material/refresh:"):
        _load_live_weather.clear()
        load_historical_weather.clear()
        st.rerun()

    _render_live_conditions()
    _render_historical_analysis()
    st.caption(
        "Sources: [Open-Meteo Forecast API](https://open-meteo.com/en/docs) · "
        "[Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)"
    )


@st.cache_data(ttl=900, show_spinner=False)
def _load_live_weather() -> dict:
    return fetch_weather()


def _render_live_conditions() -> None:
    st.header("Live conditions")
    try:
        record = _load_live_weather()
        payload = record["payload"]
        current = payload["current"]
        code = current.get("weather_code")
        condition = weather_label(int(code), "en") if code is not None else "Not reported"
        with st.container(border=True):
            st.subheader("Ulaanbaatar · Open-Meteo Forecast API")
            with st.container(horizontal=True):
                st.metric("Temperature", _format_value(current.get("temperature_c"), " °C"), border=True)
                st.metric("Feels like", _format_value(current.get("apparent_c"), " °C"), border=True)
                st.metric("Precipitation", _format_value(current.get("precipitation_mm"), " mm"), border=True)
                st.metric("Wind", _format_value(current.get("wind_speed"), " m/s"), border=True)
            st.caption(
                f"{condition} · Report time {current.get('time', 'not reported')} · "
                f"{LATITUDE:.3f}, {LONGITUDE:.3f} · Asia/Ulaanbaatar · Cached for 15 minutes"
            )
        _render_today_vs_historical(payload.get("daily", []))
    except Exception as exc:
        st.warning("Live weather could not be loaded. No values have been substituted.", icon=":material/cloud_off:")
        with st.expander("Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _render_today_vs_historical(forecast_days: list) -> None:
    """Connect today's forecast to the observed ERA5 same-month reference."""
    if not forecast_days or not isinstance(forecast_days[0], dict):
        st.info("Today's forecast is unavailable, so no historical comparison is shown.")
        return

    today = forecast_days[0]
    date = pd.to_datetime(today.get("date"), errors="coerce")
    if pd.isna(date):
        st.info("Today's forecast date is unavailable, so no historical comparison is shown.")
        return

    try:
        historical = load_historical_weather()
    except Exception:
        st.info("Historical comparison is unavailable. The live reading above is unchanged.")
        return

    reference = historical[
        historical["year"].between(BASELINE_START, BASELINE_END)
        & historical["month"].eq(date.month)
    ]
    mean_temperature = reference["temperature_c"].mean()
    mean_precipitation = reference["precipitation_mm"].mean()
    temperature_days = int(reference["temperature_c"].count())
    precipitation_days = int(reference["precipitation_mm"].count())
    forecast_temperature = today.get("temp_mean")
    forecast_precipitation = today.get("precip_sum")

    st.subheader("Today's weather in historical context")
    st.caption(
        f"{date:%B %d, %Y} forecast compared with the average daily value for {date:%B} "
        f"in {BASELINE_START}–{BASELINE_END}. This connects the live Ulaanbaatar setting "
        "to the historical charts below; weather does not affect game rules."
    )
    temperature_delta = (
        f"{float(forecast_temperature) - float(mean_temperature):+.1f} °C vs monthly daily average"
        if forecast_temperature is not None and not pd.isna(mean_temperature)
        else "Historical or forecast value unavailable"
    )
    precipitation_delta = (
        f"{float(forecast_precipitation) - float(mean_precipitation):+.1f} mm vs monthly daily average"
        if forecast_precipitation is not None and not pd.isna(mean_precipitation)
        else "Historical or forecast value unavailable"
    )
    with st.container(horizontal=True):
        st.metric(
            "Forecast daily mean temperature",
            _format_value(forecast_temperature, " °C"),
            temperature_delta,
            border=True,
        )
        st.metric(
            "Forecast daily precipitation",
            _format_value(forecast_precipitation, " mm"),
            precipitation_delta,
            border=True,
        )
    st.caption(
        f"Historical same-month daily averages: "
        f"{_format_value(mean_temperature, ' °C')} temperature and "
        f"{_format_value(mean_precipitation, ' mm')} precipitation "
        f"({temperature_days} valid temperature days; {precipitation_days} valid precipitation days). "
        "Forecast and ERA5 are different "
        "weather products, so this is a descriptive comparison, not a station measurement."
    )


def _render_historical_analysis() -> None:
    st.header("Historical analysis")
    try:
        daily = load_historical_weather()
        annual = summarize_annual_weather(daily)
        seasonal = summarize_seasonal_weather(daily)
        if annual.empty or seasonal.empty:
            st.info("No usable historical weather records were returned.")
            return

        all_years = sorted(int(year) for year in annual["year"].dropna().unique())
        controls = st.columns([1, 1], vertical_alignment="bottom")
        with controls[0]:
            year_range = st.slider(
                "Year range",
                min_value=all_years[0],
                max_value=all_years[-1],
                value=(all_years[0], all_years[-1]),
                key="insights_year_range",
            )
        with controls[1]:
            selected_seasons = st.multiselect(
                "Seasons to compare",
                options=list(SEASONS),
                default=list(SEASONS),
                key="insights_seasons",
            )

        selected_annual = annual[annual["year"].between(*year_range)].copy()
        selected_seasonal = seasonal[
            seasonal["year"].between(*year_range)
            & seasonal["season"].isin(selected_seasons)
        ].copy()
        baseline_annual = annual[
            annual["year"].between(BASELINE_START, BASELINE_END)
        ]
        baseline_temperature = baseline_annual["mean_temperature"].mean()
        baseline_precipitation = baseline_annual["total_precipitation"].mean()
        if pd.isna(baseline_temperature) or pd.isna(baseline_precipitation):
            st.info("The reference period is incomplete, so baseline comparisons cannot be calculated.")
            return

        selected_annual["temperature_anomaly"] = (
            selected_annual["mean_temperature"] - baseline_temperature
        )
        selected_annual["precipitation_anomaly"] = (
            selected_annual["total_precipitation"] - baseline_precipitation
        )
        selected_seasonal = _add_seasonal_anomalies(
            selected_seasonal, seasonal
        )

        _render_summary_metrics(selected_annual, baseline_temperature, baseline_precipitation)
        _render_plain_language_finding(
            selected_annual, baseline_temperature, baseline_precipitation
        )
        _render_annual_charts(
            selected_annual, baseline_temperature, baseline_precipitation
        )
        _render_seasonal_charts(selected_seasonal)
        _render_coverage_and_downloads(daily, selected_annual, selected_seasonal)
    except Exception as exc:
        st.error("Historical weather data could not be loaded.")
        with st.expander("Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _add_seasonal_anomalies(
    selected: pd.DataFrame,
    all_seasons: pd.DataFrame,
) -> pd.DataFrame:
    baseline_seasons = all_seasons[
        all_seasons["year"].between(BASELINE_START, BASELINE_END)
    ].groupby("season", as_index=False).agg(
        baseline_temperature=("mean_temperature", "mean"),
        baseline_precipitation=("total_precipitation", "mean"),
    )
    result = selected.merge(baseline_seasons, on="season", how="left")
    result["temperature_anomaly"] = (
        result["mean_temperature"] - result["baseline_temperature"]
    )
    result["precipitation_anomaly"] = (
        result["total_precipitation"] - result["baseline_precipitation"]
    )
    return result


def _render_summary_metrics(
    selected: pd.DataFrame,
    baseline_temperature: float,
    baseline_precipitation: float,
) -> None:
    if selected.empty:
        st.info("No annual records match this year range.")
        return
    mean_temperature = selected["mean_temperature"].mean()
    mean_precipitation = selected["total_precipitation"].mean()
    mean_coverage = selected["temperature_coverage_pct"].mean()
    with st.container(horizontal=True):
        st.metric(
            "Temperature difference vs 1991–2020",
            _format_value(mean_temperature - baseline_temperature, " °C", signed=True),
            border=True,
        )
        st.metric(
            "Mean annual precipitation",
            _format_value(mean_precipitation, " mm"),
            f"vs. {baseline_precipitation:.1f} mm reference average",
            border=True,
        )
        st.metric(
            "Mean temperature data coverage",
            _format_value(mean_coverage, "%"),
            "valid daily values in selected years",
            border=True,
        )


def _render_plain_language_finding(
    selected: pd.DataFrame,
    baseline_temperature: float,
    baseline_precipitation: float,
) -> None:
    if selected.empty:
        return
    period_temperature = selected["mean_temperature"].mean()
    period_precipitation = selected["total_precipitation"].mean()
    observations = []
    if pd.notna(period_temperature):
        temp_difference = period_temperature - baseline_temperature
        direction = "higher" if temp_difference >= 0 else "lower"
        observations.append(
            f"mean annual temperature was {abs(temp_difference):.2f} °C {direction} than the reference average"
        )
    if pd.notna(period_precipitation):
        precipitation_difference = period_precipitation - baseline_precipitation
        direction = "more" if precipitation_difference >= 0 else "less"
        observations.append(
            f"mean annual precipitation was {abs(precipitation_difference):.1f} mm {direction} than the reference average"
        )
    if not observations:
        st.info("No complete measurements are available for an interpretation in this year range.")
        return
    st.info(
        f"Across {int(selected['year'].min())}–{int(selected['year'].max())}, "
        + "; ".join(observations)
        + ". Both comparisons use the 1991–2020 reference period. They are descriptive for one reanalysis grid point and do not establish a cause."
    )


def _render_annual_charts(
    annual: pd.DataFrame,
    baseline_temperature: float,
    baseline_precipitation: float,
) -> None:
    st.subheader("Year-by-year patterns")
    st.caption(
        "Each point summarizes one year. The dashed line marks the 1991–2020 average; "
        "the difference charts show how far each year sits above or below it."
    )
    if annual.empty:
        st.info("No annual records match this year range.")
        return
    left, right = st.columns(2)
    temperature_figure = px.line(
        annual,
        x="year",
        y="mean_temperature",
        markers=True,
        title="Annual mean temperature",
        labels={"year": "Year", "mean_temperature": "Mean temperature (°C)"},
        template="plotly_dark",
    )
    temperature_figure.add_hline(
        y=baseline_temperature,
        line_dash="dash",
        annotation_text="1991–2020 reference",
    )
    left.plotly_chart(
        temperature_figure,
        width="stretch",
        alt="Annual mean temperature with the 1991–2020 reference average",
    )

    precipitation_figure = px.bar(
        annual,
        x="year",
        y="total_precipitation",
        title="Annual total precipitation",
        labels={"year": "Year", "total_precipitation": "Precipitation (mm)"},
        template="plotly_dark",
    )
    precipitation_figure.add_hline(
        y=baseline_precipitation,
        line_dash="dash",
        annotation_text="1991–2020 reference",
    )
    right.plotly_chart(
        precipitation_figure,
        width="stretch",
        alt="Annual precipitation totals compared with the 1991–2020 average",
    )


def _render_seasonal_charts(seasonal: pd.DataFrame) -> None:
    st.subheader("Seasonal differences from the 1991–2020 reference")
    st.caption(
        "Each line follows one meteorological season across years: winter (Dec–Feb), "
        "spring (Mar–May), summer (Jun–Aug), and autumn (Sep–Nov). Values above zero "
        "are warmer or wetter than that season's 1991–2020 average; values below zero are cooler or drier."
    )
    if seasonal.empty:
        st.info("Choose at least one season to compare.")
        return
    left, right = st.columns(2)
    temperature_figure = px.line(
        seasonal,
        x="year",
        y="temperature_anomaly",
        color="season",
        markers=True,
        title="Seasonal temperature difference",
        labels={
            "year": "Season year",
            "temperature_anomaly": "Difference (°C)",
            "season": "Season",
        },
        category_orders={"season": list(SEASONS)},
        template="plotly_dark",
    )
    temperature_figure.add_hline(y=0, line_dash="dash")
    left.plotly_chart(
        temperature_figure,
        width="stretch",
        alt="Seasonal temperature differences above or below the 1991–2020 reference",
    )

    precipitation_figure = px.line(
        seasonal,
        x="year",
        y="precipitation_anomaly",
        color="season",
        markers=True,
        title="Seasonal precipitation difference",
        labels={
            "year": "Season year",
            "precipitation_anomaly": "Difference (mm)",
            "season": "Season",
        },
        category_orders={"season": list(SEASONS)},
        template="plotly_dark",
    )
    precipitation_figure.add_hline(y=0, line_dash="dash")
    right.plotly_chart(
        precipitation_figure,
        width="stretch",
        alt="Seasonal precipitation differences above or below the 1991–2020 reference",
    )


def _render_coverage_and_downloads(
    daily: pd.DataFrame,
    annual: pd.DataFrame,
    seasonal: pd.DataFrame,
) -> None:
    st.subheader("Data quality and records")
    st.caption(
        "Coverage is the share of calendar days with a real value for that variable. It is shown separately for temperature and precipitation."
    )
    coverage = annual[
        [
            "year",
            "temperature_days",
            "temperature_coverage_pct",
            "precipitation_days",
            "precipitation_coverage_pct",
        ]
    ].rename(
        columns={
            "year": "Year",
            "temperature_days": "Temperature days",
            "temperature_coverage_pct": "Temperature coverage (%)",
            "precipitation_days": "Precipitation days",
            "precipitation_coverage_pct": "Precipitation coverage (%)",
        }
    )
    st.dataframe(
        coverage,
        width="stretch",
        hide_index=True,
        alt="Yearly valid-day counts and data coverage for each weather variable",
    )
    with st.expander("Seasonal coverage details"):
        seasonal_coverage = seasonal[
            [
                "year",
                "season",
                "temperature_days",
                "temperature_coverage_pct",
                "precipitation_days",
                "precipitation_coverage_pct",
            ]
        ].rename(
            columns={
                "year": "Season year",
                "season": "Season",
                "temperature_days": "Temperature days",
                "temperature_coverage_pct": "Temperature coverage (%)",
                "precipitation_days": "Precipitation days",
                "precipitation_coverage_pct": "Precipitation coverage (%)",
            }
        )
        st.dataframe(
            seasonal_coverage,
            width="stretch",
            hide_index=True,
            alt="Seasonal valid-day counts and data coverage for each weather variable",
        )
    with st.container(horizontal=True, vertical_alignment="center"):
        st.download_button(
            "Download annual summary CSV",
            data=annual.to_csv(index=False).encode("utf-8-sig"),
            file_name="ulaanbaatar_annual_weather_summary.csv",
            mime="text/csv",
            icon=":material/download:",
        )
        st.download_button(
            "Download seasonal summary CSV",
            data=seasonal.to_csv(index=False).encode("utf-8-sig"),
            file_name="ulaanbaatar_seasonal_weather_summary.csv",
            mime="text/csv",
            icon=":material/download:",
        )
        show_daily = st.toggle("Show cleaned daily data", key="show_cleaned_weather_data")
        if show_daily:
            st.download_button(
                "Download daily records CSV",
                data=daily.to_csv(index=False).encode("utf-8-sig"),
                file_name="ulaanbaatar_daily_weather_era5.csv",
                mime="text/csv",
                icon=":material/download:",
            )
    if show_daily:
        st.dataframe(
            daily,
            width="stretch",
            hide_index=True,
            alt="Cleaned daily Open-Meteo ERA5 data for Ulaanbaatar",
        )


def _format_value(value: object, suffix: str = "", signed: bool = False) -> str:
    if value is None or pd.isna(value):
        return "—"
    number = float(value)
    formatted = f"{number:+.1f}" if signed else f"{number:.1f}"
    return f"{formatted}{suffix}"
