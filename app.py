"""Magic Town Mafia entry point with separate game and insights pages."""

from __future__ import annotations

import streamlit as st

from magic_town.data_insights import render_data_insights
from magic_town.game_lobby import render_game_lobby


def _language() -> str:
    if "lang" not in st.session_state:
        st.session_state["lang"] = "en"
    st.markdown(
        """
        <style>
        [data-testid="stSegmentedControl"] { width:100% !important; }
        [data-testid="stSegmentedControl"] [role="radiogroup"] {
            display:flex !important; width:100% !important; gap:.35rem !important;
        }
        [data-testid="stSegmentedControl"] button {
            flex:1 1 0 !important; min-width:7rem !important; min-height:3.15rem !important;
            padding:.55rem 1rem !important; font-size:1.05rem !important;
            font-weight:700 !important; border-radius:12px !important;
        }
        [data-testid="stSegmentedControl"] label {
            font-size:1rem !important; font-weight:650 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    location_column, language_column = st.columns([7, 2], vertical_alignment="center")
    with location_column:
        st.caption("📍 Улаанбаатар · Монгол" if st.session_state["lang"] == "mn" else "📍 Ulaanbaatar · Mongolia")
    with language_column:
        st.segmented_control(
            "Хэл / Language",
            options=["mn", "en"],
            format_func=lambda code: "Монгол" if code == "mn" else "English",
            key="lang",
            width="stretch",
        )
    return st.session_state.get("lang", "en")


def _game_page() -> None:
    render_game_lobby(_language())


def _insights_page() -> None:
    render_data_insights("en")


def main() -> None:
    st.set_page_config(
        page_title="Magic Town Mafia",
        page_icon=":material/masks:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    if "lang" not in st.session_state:
        st.session_state["lang"] = "en"
    pages = [
        st.Page(
            _game_page,
            title="Game",
            icon=":material/sports_esports:",
            url_path="game",
            default=True,
        ),
        st.Page(
            _insights_page,
            title="Data & Insights",
            icon=":material/monitoring:",
            url_path="data-insights",
        ),
    ]
    st.navigation(pages, position="sidebar").run()


if __name__ == "__main__":
    main()
