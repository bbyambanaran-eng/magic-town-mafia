import secrets
import string
import random
import html
import base64
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from .supabase_client import get_supabase_client
from .plants import fetch_plants
from .weather import fetch_weather, weather_label

ROOM_CAPACITY = 12
ASSET_DIR = Path(__file__).parent / "assets"
PUBLIC_CHARACTER_PORTRAITS = (
    "characters/mafia.webp",
    "characters/doctor.webp",
    "characters/detective.webp",
    "characters/citizen_male.webp",
    "characters/citizen_female.webp",
)


def _render_player_seats(players: list[dict], room_id: str, lang: str) -> None:
    """Show public character portraits assigned independently from secret roles."""
    contestants = [player for player in players if not player.get("is_host")]
    if not contestants:
        return

    # Seed by room so all clients see the same portrait at each seat. The shuffle
    # never reads role data, so public portraits cannot disclose a secret role.
    shuffled = list(contestants)
    random.Random(f"public-portraits:{room_id}").shuffle(shuffled)
    portraits = {
        player["id"]: PUBLIC_CHARACTER_PORTRAITS[index % len(PUBLIC_CHARACTER_PORTRAITS)]
        for index, player in enumerate(shuffled)
    }

    # Clockwise positions around the central town-table emblem (up to 12 seats).
    ring_positions = (
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5),
        (2, 5), (3, 5), (3, 4), (3, 3), (3, 2), (3, 1), (2, 1),
    )
    cells = []
    for index, player in enumerate(contestants[:ROOM_CAPACITY]):
        row, col = ring_positions[index]
        portrait = _brand_asset(portraits[player["id"]])
        seat_label = f"Тоглогч {index + 1}" if lang == "mn" else f"Player {index + 1}"
        if not player.get("is_alive", True):
            status = "Хасагдсан" if lang == "mn" else "Eliminated"
        else:
            status = "Тоглож байна" if lang == "mn" else "Playing"
        cells.append(
            f'<article class="mt-seat" style="grid-row:{row};grid-column:{col}">'
            f'<img src="data:image/webp;base64,{portrait}" alt="Character portrait" />'
            f'<div class="mt-seat-name">{seat_label}</div>'
            f'<div class="mt-seat-status">{status}</div></article>'
        )

    host_label = "Хотын дарга" if lang == "mn" else "Mayor"
    center = (
        '<div class="mt-table-center" style="grid-row:2;grid-column:2 / 5">'
        '<span>🌆</span><strong>Magic Town Mafia</strong>'
        f'<small>{host_label}</small>'
        '</div>'
    )
    st.markdown(
        """
        <style>
        .mt-seat-board{display:grid;grid-template-columns:repeat(5,minmax(92px,1fr));
            grid-template-rows:repeat(3,minmax(145px,auto));gap:.6rem;margin:.6rem 0 1rem;
            padding:1rem;border:1px solid #d9b65e55;border-radius:18px;
            background:radial-gradient(ellipse at center,#26384b 0,#111c2b 70%);}
        .mt-seat{min-width:0;overflow:hidden;text-align:center;border:1px solid #d9b65e66;
            border-radius:13px;background:#101a29eF;box-shadow:0 5px 16px #0006;}
        .mt-seat img{display:block;width:100%;height:112px;object-fit:cover;object-position:center 28%;}
        .mt-seat-name{padding:.35rem .25rem 0;color:#fff1c4;font-weight:700;overflow-wrap:anywhere;}
        .mt-seat-status{padding:0 .2rem .35rem;color:#d5dfeb;font-size:.76rem;}
        .mt-table-center{align-self:center;justify-self:center;display:flex;flex-direction:column;
            align-items:center;justify-content:center;gap:.3rem;width:72%;min-height:100px;
            border:1px solid #d9b65e88;border-radius:999px;text-align:center;
            color:#f5d98e;background:radial-gradient(ellipse,#31445a,#172536 72%);
            box-shadow:0 0 25px #d9b65e22;}
        .mt-table-center span{font-size:1.4rem}.mt-table-center small{color:#d9e1eb}
        @media(max-width:700px){.mt-seat-board{grid-template-columns:repeat(3,minmax(75px,1fr));
            grid-template-rows:none;gap:.4rem;padding:.55rem}.mt-seat{grid-row:auto!important;grid-column:auto!important}
            .mt-seat img{height:100px}.mt-table-center{display:none}}
        </style>
        """
        + '<section class="mt-seat-board">'
        + "".join(cells)
        + center
        + "</section>",
        unsafe_allow_html=True,
    )


def _private_role_portrait(role: str, player_id: str) -> str:
    """Resolve a role portrait for the current viewer only."""
    if role == "mafia":
        return "characters/mafia.webp"
    if role == "doctor":
        return "characters/doctor.webp"
    if role == "detective":
        return "characters/detective.webp"
    citizen_portraits = ("characters/citizen_male.webp", "characters/citizen_female.webp")
    return random.Random(f"private-citizen:{player_id}").choice(citizen_portraits)


@st.cache_data
def _brand_asset(filename: str) -> str:
    return base64.b64encode((ASSET_DIR / filename).read_bytes()).decode("ascii")


def _render_brand_banner(lang: str) -> None:
    mn = lang == "mn"
    local_now = datetime.now(ZoneInfo("Asia/Ulaanbaatar"))
    day = 6 <= local_now.hour < 19
    phase = ("☀️ Өдөр" if day else "🌙 Шөнө") if mn else ("☀️ Day" if day else "🌙 Night")
    logo = _brand_asset("aum_shield.png")
    skyline = _brand_asset("ulaanbaatar_skyline.svg")
    st.markdown(
        f"""
        <style>
        .magic-town-hero {{
            position: relative; isolation: isolate; overflow: hidden;
            min-height: 166px; margin: 0 0 1rem; padding: 1.1rem 1.4rem;
            display: grid; grid-template-columns: 1fr 142px 1fr; align-items: center;
            border: 1px solid rgba(225,190,103,.42); border-radius: 18px;
            background: linear-gradient(110deg,rgba(7,16,31,.97),rgba(17,31,52,.79) 52%,rgba(7,16,31,.96));
            box-shadow: 0 14px 38px rgba(0,0,0,.2);
        }}
        .magic-town-hero .magic-skyline {{
            position: absolute; inset: auto 0 0; width: 100%; height: 158px;
            object-fit: cover; object-position: center bottom; opacity: .88; z-index: -1;
        }}
        .magic-town-brand {{ color:#f0d182 !important; font-size:clamp(1.15rem,2.1vw,1.65rem); font-weight:750; text-shadow:0 2px 14px #000; }}
        .magic-town-kicker {{ margin-top:.4rem; color:#e4eaf1 !important; font-size:.93rem; text-shadow:0 2px 10px #000; }}
        .magic-town-emblem {{
            width:112px; height:112px; margin:auto; padding:8px; box-sizing:border-box;
            border-radius:50%; background:radial-gradient(circle,#fff9df 0 48%,#d9b65e 52%,#80652c 66%,transparent 71%);
            box-shadow:0 0 28px #e8c55e66; display:flex; align-items:center; justify-content:center;
        }}
        .magic-town-emblem img {{ width:72px; height:86px; object-fit:contain; border-radius:10px; box-shadow:0 0 0 2px #e4c369; }}
        .magic-town-phase {{ justify-self:end; padding:.55rem .9rem; border:1px solid #d9b65e88; border-radius:999px; color:#f5d98e !important; background:#111d31dd; font-weight:700; box-shadow:0 0 18px #d4ad4b33; }}
        @media (max-width:620px) {{
            .magic-town-hero {{ min-height:132px; grid-template-columns:1fr 78px; padding:.85rem; }}
            .magic-town-emblem {{ grid-column:2; grid-row:1; width:72px; height:72px; }}
            .magic-town-emblem img {{ width:48px; height:58px; }}
            .magic-town-phase {{ grid-column:1 / -1; justify-self:start; margin-top:.55rem; }}
        }}
        </style>
        <section class="magic-town-hero">
            <img class="magic-skyline" src="data:image/svg+xml;base64,{skyline}" alt="Ulaanbaatar skyline at night" />
            <div>
                <div class="magic-town-brand">🌆 Magic Town Mafia</div>
                <div class="magic-town-kicker">{"Улаанбаатарын бодит цаг агаар" if mn else "Live Ulaanbaatar weather"}</div>
            </div>
            <div class="magic-town-emblem"><img src="data:image/png;base64,{logo}" alt="American University of Mongolia shield" /></div>
            <div class="magic-town-phase">{phase}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=900, show_spinner=False)
def _game_weather(day_key: str) -> dict:
    # Include Ulaanbaatar local date in the cache key so midnight starts a fresh fetch.
    return fetch_weather()


@st.cache_data(ttl=1800, show_spinner=False)
def _game_plants() -> dict:
    return fetch_plants()


def _render_real_world_context(lang: str, game_phase: str) -> None:
    mn = lang == "mn"
    local_zone = ZoneInfo("Asia/Ulaanbaatar")
    now_local = datetime.now(local_zone).replace(tzinfo=None)
    today_key = now_local.date().isoformat()
    try:
        record = _game_weather(today_key)
        payload = record["payload"]
        current = payload["current"]
        today = next(
            (day for day in payload["daily"] if day.get("date") == today_key),
            None,
        )
        if today is None:
            st.info(
                f"{today_key} өдрийн цаг агаарын дата одоогоор ирээгүй байна."
                if mn else f"Weather data for {today_key} has not arrived yet."
            )
            return
        # The shared town theme follows the game phase. Open-Meteo still supplies
        # the real weather values and the real sunrise/sunset shown below.
        is_daylight = game_phase != "night"
        weather_code = int(current["weather_code"])
        wind_speed = current.get("wind_speed")
        cloud_cover = current.get("cloud_pct")
        _apply_weather_theme(
            is_daylight,
            weather_code,
            wind_speed if isinstance(wind_speed, (int, float)) else None,
            cloud_cover if isinstance(cloud_cover, (int, float)) else None,
        )

        sky = (
            ("☀️ Өдөр" if is_daylight else "🌙 Шөнө")
            if mn else ("☀️ Day" if is_daylight else "🌙 Night")
        )
        condition = weather_label(weather_code, lang)
        temp = current.get("temperature_c")
        temp_text = f"{temp:.1f} °C" if isinstance(temp, (int, float)) else "—"
        wind_text = f"{wind_speed:.1f} m/s" if isinstance(wind_speed, (int, float)) else "—"
        low, high = today.get("temp_min"), today.get("temp_max")
        forecast = (
            f"{low:.1f}° – {high:.1f}°C" if isinstance(low, (int, float)) and isinstance(high, (int, float))
            else "—"
        )
        first, second, third, fourth = st.columns(4)
        first.metric("Одоо" if mn else "Now", temp_text)
        second.metric("Тэнгэр" if mn else "Conditions", condition)
        third.metric("Салхи" if mn else "Wind", wind_text)
        fourth.metric("Тоглоомын үе" if mn else "Game phase", sky)
        st.caption(
            f"Огноо: {today['date']} · Өнөөдрийн хэм: {forecast} · Open-Meteo · мэдээний цаг {current['time']} · нар мандах {today['sunrise'][-5:]} / жаргах {today['sunset'][-5:]}"
            if mn else
            f"Date: {today['date']} · Today's range: {forecast} · Open-Meteo · report time {current['time']} · sunrise {today['sunrise'][-5:]} / sunset {today['sunset'][-5:]}"
        )
    except Exception:
        st.info(
            "Цаг агаарын бодит дата ирээгүй тул theme өөрчлөөгүй. Тоглоом хэвийн үргэлжилнэ."
            if mn else
            "Live weather is unavailable, so the weather theme was not changed. The game continues."
        )


def _apply_weather_theme(
    is_daylight: bool,
    weather_code: int,
    wind_speed: float | None,
    cloud_cover: float | None,
) -> None:
    snow_codes = {71, 73, 75, 77, 85, 86}
    rain_codes = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    cloud_codes = {2, 3, 45, 48}
    is_snowing = weather_code in snow_codes
    is_raining = weather_code in rain_codes
    is_windy = wind_speed is not None and wind_speed >= 8.0
    is_cloudy = weather_code in cloud_codes or (cloud_cover is not None and cloud_cover >= 75)

    if is_daylight:
        celestial = "radial-gradient(circle at 86% 10%, #ffe89b 0 38px, #ffe89b66 40px 70px, transparent 72px)"
        sky = "linear-gradient(180deg, #5b9fca 0%, #a9d7e8 52%, #71917c 100%)"
        if is_snowing:
            sky = "linear-gradient(180deg, #829daf 0%, #bacbd3 50%, #748895 100%)"
        elif is_raining:
            sky = "linear-gradient(180deg, #475968 0%, #687b84 52%, #43545a 100%)"
        elif is_cloudy:
            sky = "linear-gradient(180deg, #667e91 0%, #a1b2b8 52%, #637b78 100%)"
    else:
        celestial = "radial-gradient(circle at 86% 10%, #f3f0d8 0 25px, #f3f0d866 27px 48px, transparent 50px)"
        sky = "linear-gradient(180deg, #101b34 0%, #18243a 52%, #10141f 100%)"
        if is_snowing:
            sky = "linear-gradient(180deg, #263647 0%, #344451 52%, #1a2631 100%)"
        elif is_raining:
            sky = "linear-gradient(180deg, #151b29 0%, #28313d 52%, #111720 100%)"
        elif is_cloudy:
            sky = "linear-gradient(180deg, #202b3c 0%, #36414b 52%, #151b25 100%)"

    clouds = (
        "radial-gradient(ellipse at 18% 17%, #e9f2f366 0 7%, transparent 18%), radial-gradient(ellipse at 43% 13%, #eef5f366 0 8%, transparent 19%), radial-gradient(ellipse at 76% 20%, #e8f0f266 0 8%, transparent 20%),"
        if is_cloudy or is_snowing or is_raining else ""
    )
    if is_snowing:
        weather_layer = """
            [data-testid="stAppViewContainer"]::before {
                content: ""; position: fixed; inset: -20vh 0 0; pointer-events: none; z-index: 0;
                background-image: radial-gradient(3px 3px at 12% 12%, #fff 98%, transparent), radial-gradient(2px 2px at 34% 42%, #fff 98%, transparent), radial-gradient(3px 3px at 59% 19%, #fff 98%, transparent), radial-gradient(2px 2px at 82% 51%, #fff 98%, transparent), radial-gradient(2px 2px at 94% 23%, #fff 98%, transparent);
                background-size: 340px 420px; opacity: .46; animation: magic-snow 12s linear infinite;
            }
            @keyframes magic-snow { from { transform: translateY(-8vh); } to { transform: translateY(24vh); } }
        """
    elif is_raining:
        weather_layer = """
            [data-testid="stAppViewContainer"]::before {
                content: ""; position: fixed; inset: -20vh 0 0; pointer-events: none; z-index: 0;
                background-image: repeating-linear-gradient(105deg, transparent 0 28px, #d9e9f244 29px 30px, transparent 31px 58px);
                opacity: .42; animation: magic-rain 1.2s linear infinite;
            }
            @keyframes magic-rain { from { transform: translateY(-8vh); } to { transform: translateY(10vh); } }
        """
    else:
        weather_layer = """
            [data-testid="stAppViewContainer"]::before {
                content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
                background-image: radial-gradient(2px 2px at 18% 16%, #fff 98%, transparent), radial-gradient(2px 2px at 39% 28%, #fff 98%, transparent), radial-gradient(2px 2px at 71% 14%, #fff 98%, transparent), radial-gradient(2px 2px at 58% 38%, #fff 98%, transparent), radial-gradient(2px 2px at 88% 31%, #fff 98%, transparent);
                opacity: .5;
            }
        """ if not is_daylight else ""

    wind_layer = """
        [data-testid="stAppViewContainer"]::after {
            content: ""; position: fixed; inset: 8vh -15vw; pointer-events: none; z-index: 0;
            background-image: repeating-linear-gradient(170deg, transparent 0 72px, #ffffff36 73px 75px, transparent 76px 142px);
            opacity: .34; animation: magic-wind 4s ease-in-out infinite alternate;
        }
        @keyframes magic-wind { from { transform: translateX(-7vw); } to { transform: translateX(7vw); } }
    """ if is_windy else ""

    game_ui_theme = """
        [data-testid="stMain"],
        [data-testid="stMain"] *:not(svg):not(path) {
            color: #f1ead7 !important;
        }
        [data-testid="stMain"] h1,
        [data-testid="stMain"] h2,
        [data-testid="stMain"] h3 {
            color: #f0cd75 !important;
        }
        [data-testid="stMain"] a { color: #9ccaff !important; }
        [data-testid="stMain"] [data-testid="stMetric"] {
            background: linear-gradient(145deg, rgba(23,36,58,.97), rgba(14,24,41,.98)) !important;
            border: 1px solid rgba(226,190,103,.72) !important;
            border-radius: 12px !important;
            padding: .65rem .8rem !important;
        }
        [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(15,25,42,.90) !important;
            border-color: rgba(226,190,103,.52) !important;
            border-radius: 14px !important;
        }
        [data-testid="stMain"] input:not([type="checkbox"]),
        [data-testid="stMain"] textarea,
        [data-testid="stMain"] [data-baseweb="select"] > div {
            color: #f3ecd9 !important;
            background-color: #17243a !important;
            border-color: #9c824a !important;
        }
        [data-testid="stMain"] input::placeholder,
        [data-testid="stMain"] textarea::placeholder {
            color: #c3baa5 !important;
            opacity: 1 !important;
        }
        [data-testid="stMain"] button,
        [data-testid="stMain"] [role="button"] {
            color: #1c2636 !important;
            border: 1px solid #f0d58f !important;
            background: linear-gradient(180deg, #f0d58f, #c59a46) !important;
            font-weight: 650 !important;
        }
        [data-testid="stMain"] button:hover,
        [data-testid="stMain"] [role="button"]:hover {
            border-color: #fff0bd !important;
            background: linear-gradient(180deg, #ffe7a5, #d5ad5d) !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #101b2c, #111827) !important;
            border-right: 1px solid rgba(226,190,103,.42) !important;
        }
    """

    navy_overlay = (
        "linear-gradient(180deg, rgba(12,21,37,.48), rgba(12,20,35,.66))"
        if is_daylight else
        "linear-gradient(180deg, rgba(8,15,29,.62), rgba(8,14,26,.76))"
    )

    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{ background: {celestial}, {clouds} {navy_overlay}, {sky}; background-attachment: fixed; }}
        [data-testid="stMain"] {{ position: relative; z-index: 1; background: transparent; }}
        [data-testid="stHeader"] {{ background: transparent; }}
        [data-testid="stSidebar"] {{ position: relative; z-index: 2; background-color: rgba(15, 18, 25, .82); }}
        {game_ui_theme}
        {weather_layer}
        {wind_layer}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _apply_doctor_plant_theme() -> None:
    """Give only the Doctor's own session a calm, botanical game backdrop."""
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(ellipse at 12% 18%, #83a96d33 0 9%, transparent 25%),
                radial-gradient(ellipse at 86% 75%, #5c8c5b33 0 12%, transparent 30%),
                linear-gradient(145deg, #10271d 0%, #1c3827 48%, #0e241b 100%) !important;
            background-attachment: fixed !important;
        }
        [data-testid="stAppViewContainer"]::before,
        [data-testid="stAppViewContainer"]::after {
            content: none !important;
            background: none !important;
            animation: none !important;
        }
        [data-testid="stMain"] p,
        [data-testid="stMain"] li,
        [data-testid="stMain"] label,
        [data-testid="stMain"] h1,
        [data-testid="stMain"] h2,
        [data-testid="stMain"] h3,
        [data-testid="stMain"] [data-testid="stMarkdownContainer"],
        [data-testid="stMain"] [data-testid="stCaptionContainer"],
        [data-testid="stMain"] [data-testid="stMetricLabel"],
        [data-testid="stMain"] [data-testid="stMetricValue"] {
            color: #e1f0e3 !important;
        }
        [data-testid="stMain"] .stButton > button {
            color: #e1f0e3 !important;
            border-color: #93b59b !important;
            background-color: rgba(11,32,22,.8) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_doctor_plant_context(lang: str, round_number: int) -> None:
    mn = lang == "mn"
    with st.container(border=True):
        st.markdown(
            "**🌿 Эмчийн ургамлын theme · Монголын бодит GBIF бүртгэл**"
            if mn else "**🌿 Doctor's plant theme · real GBIF record from Mongolia**"
        )
        try:
            record = _game_plants()
            payload = record["payload"]
            named_records = [
                item for item in payload.get("records", [])
                if item.get("scientific_name")
            ]
            if not named_records:
                st.info(
                    "GBIF нэртэй ургамлын бүртгэл ирүүлсэнгүй."
                    if mn else "GBIF returned no named plant record."
                )
                return

            item = named_records[(max(1, round_number) - 1) % len(named_records)]
            plant_name = html.escape(str(item["scientific_name"]))
            details = [
                html.escape(str(value)) for value in (
                    item.get("family"), item.get("state_province"),
                    item.get("locality"), item.get("event_date"),
                ) if value
            ]
            record_url = item.get("occurrence_url") or ""
            link = (
                f'<a href="{html.escape(record_url, quote=True)}" target="_blank">'
                f'{"GBIF ажиглалтын бүртгэл" if mn else "GBIF occurrence record"}</a>'
                if record_url.startswith("https://") else ""
            )
            st.markdown(
                '<div style="padding:1rem 1.2rem;border-radius:12px;'
                'border:1px solid #4f805d;background:linear-gradient(135deg,#123528,#213e2d);">'
                f'<div style="font-size:1.25rem;font-weight:700;color:#b7efc5">🌿 {plant_name}</div>'
                f'<div style="margin-top:.45rem;color:#d5e9d8">{" · ".join(details)}</div>'
                f'<div style="margin-top:.55rem">{link}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Зөвхөн эмчид харагдана; ургамлын дата эмчлэх чадварт нөлөөлөхгүй. GBIF бүртгэл нь ургамлын тоо толгой биш."
                if mn else
                "Visible only to the Doctor; plant data does not affect the protect action. GBIF records are not population counts."
            )
        except Exception:
            st.info(
                "GBIF-ийн ургамлын дата одоогоор ачаалсангүй."
                if mn else "GBIF plant data is unavailable right now."
            )

@st.fragment(run_every="3s")
def render_game_lobby(lang: str) -> None:
    mn = lang == "mn"
    _render_brand_banner(lang)

    try:
        db = get_supabase_client()
    except Exception as exc:
        st.error("Supabase холболт амжилтгүй." if mn else "Supabase connection failed.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")
        return

    room_id = st.session_state.get("mafia_room_id")
    player_id = st.session_state.get("mafia_player_id")

    if room_id:
        _render_current_room(db, room_id, player_id, lang)
        return

    _render_real_world_context(lang, "lobby")
    _render_create_join(db, lang)


def _render_current_room(db, room_id: str, player_id: str, lang: str) -> None:
    mn = lang == "mn"

    try:
        rooms = (
            db.table("game_rooms")
            .select("*")
            .eq("id", room_id)
            .limit(1)
            .execute()
            .data
        )

        if not rooms:
            st.session_state.pop("mafia_room_id", None)
            st.session_state.pop("mafia_player_id", None)
            st.rerun()
            return

        room = rooms[0]
        players = (
            db.table("game_players")
            .select("id, name, role, is_host, is_alive")
            .eq("room_id", room_id)
            .order("joined_at")
            .execute()
            .data
        )
        contestants = [p for p in players if not p.get("is_host")]

        st.write("Өрөөний код" if mn else "Room code")
        st.code(room["code"])
        st.write(
            f"{'Тоглогчид' if mn else 'Players'}: "
            f"{len(contestants)} / {ROOM_CAPACITY}"
        )
        _render_player_seats(players, room_id, lang)

        # Role name and its matching portrait are rendered only in this viewer's
        # own Streamlit session; public seat portraits above are role-independent.
        current_player = next(
            (player for player in players if player["id"] == player_id),
            None,
        )
        if current_player and current_player.get("role"):
            role_names = {
                "mafia": ("Мафийн тал", "Mafia"),
                "doctor": ("Эмч", "Doctor"),
                "detective": ("Цагдаа", "Detective"),
                "citizen": ("Иргэн", "Citizen"),
            }
            role_name = role_names.get(current_player["role"], ("Тоглогч", "Player"))[0 if mn else 1]
            st.image(
                ASSET_DIR / _private_role_portrait(current_player["role"], str(player_id)),
                width=190,
            )
            st.success(
                f"Таны нууц дүр: {role_name}"
                if mn
                else f"Your secret role: {role_name}"
            )

        phase = room.get("phase", "lobby")
        _render_real_world_context(lang, phase)
        current_player = next(
            (player for player in players if player["id"] == player_id),
            None,
        )
        if current_player and current_player.get("role") == "doctor":
            _apply_doctor_plant_theme()
        is_host = bool(current_player and current_player.get("is_host"))

        if (
            phase in {"day", "night"}
            and current_player
            and not is_host
            and current_player.get("is_alive", True)
        ):
            if st.button(
                "Тоглоомоос гарах" if mn else "Leave game",
                key=f"leave_mafia_game_{player_id}",
            ):
                try:
                    db.table("game_players").update({"is_alive": False}).eq(
                        "id", player_id
                    ).execute()
                    after_leave = [
                        {**p, "is_alive": False} if p["id"] == player_id else p
                        for p in players
                    ]
                    winner = _game_winner(after_leave)
                    if winner:
                        db.table("game_rooms").update({"phase": "finished"}).eq(
                            "id", room_id
                        ).execute()
                    leave_event = (
                        f"📣 {current_player['name']} тоглоомоос гарлаа. "
                        f"{'Иргэд яллаа!' if winner == 'citizens' else 'Мафийн тал яллаа!' if winner == 'mafia' else 'Үлдсэн тоглогчид үргэлжлүүлнэ.'}"
                        if mn else
                        f"📣 {current_player['name']} left the game. "
                        f"{'The citizens win!' if winner == 'citizens' else 'The Mafia wins!' if winner == 'mafia' else 'The remaining players continue.'}"
                    )
                    _record_public_event(db, room_id, players, leave_event)
                    st.rerun()
                except Exception as exc:
                    st.error("Тоглоомоос гаргаж чадсангүй." if mn else "Could not leave the game.")
                    with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                        st.code(f"{type(exc).__name__}: {exc}")

        if phase != "lobby":
            _render_latest_public_event(db, room_id, players)

        if phase == "lobby":
            if is_host:
                if st.button(
                    "🎮 Тоглоом эхлүүлэх" if mn else "🎮 Start game",
                    key="start_mafia_game",
                ):
                    if len(contestants) < 2:
                        st.warning(
                            "Эхлэхэд дор хаяж 2 тоглогч хэрэгтэй."
                            if mn
                            else "At least 2 players are needed to start."
                        )
                    else:
                        shuffled = [player["id"] for player in contestants]
                        random.shuffle(shuffled)
                        assigned = {participant_id: "citizen" for participant_id in shuffled}
                        mafia_count = max(1, len(contestants) // 6)
                        cursor = 0
                        for player_id_to_assign in shuffled[:mafia_count]:
                            assigned[player_id_to_assign] = "mafia"
                        cursor += mafia_count
                        if len(contestants) >= 3:
                            assigned[shuffled[cursor]] = "doctor"
                            cursor += 1
                        if len(contestants) >= 5:
                            assigned[shuffled[cursor]] = "detective"

                        for player in contestants:
                            db.table("game_players").update({
                                "role": assigned[player["id"]]
                            }).eq("id", player["id"]).execute()
                        for host in players:
                            if host.get("is_host"):
                                db.table("game_players").update({"role": None}).eq(
                                    "id", host["id"]
                                ).execute()

                        db.table("game_rooms").update({
                            "phase": "night", "round_number": 1
                        }).eq("id", room_id).execute()
                        st.rerun()
            else:
                st.info(
                    "Өрөөний эзэн тоглоом эхлүүлэхийг хүлээж байна."
                    if mn
                    else "Waiting for the host to start the game."
                )

        elif phase == "day":
            st.info(
                f"Тоглоом эхэллээ · Өдөр · Раунд {room.get('round_number', 1)}"
                if mn
                else f"Game started · Day · Round {room.get('round_number', 1)}"
            )
            _render_day_chat_and_vote(
                db, room_id, player_id, players,
                int(room.get("round_number", 1)), is_host, lang,
            )
            if is_host:
                _render_mayor_night_report(
                    db, room_id, players,
                    int(room.get("round_number", 1)), lang,
                )
            _render_detective_action(
                db, room_id, player_id, players,
                int(room.get("round_number", 1)), lang,
            )
        elif phase == "night":
            st.info(
                f"Тоглоом эхэллээ · Шөнө · Раунд {room.get('round_number', 1)}"
                if mn
                else f"Game started · Night · Round {room.get('round_number', 1)}"
            )
            _render_night(
                db, room_id, player_id, players,
                int(room.get("round_number", 1)), is_host, lang,
            )
        elif phase == "finished":
            winner = _game_winner(players)
            if mn:
                st.success("Мафийн тал яллаа!" if winner == "mafia" else "Иргэд яллаа!")
            else:
                st.success("The Mafia wins!" if winner == "mafia" else "The citizens win!")
            role_names = {
                "mafia": ("Мафийн тал", "Mafia"),
                "doctor": ("Эмч", "Doctor"),
                "detective": ("Цагдаа", "Detective"),
                "citizen": ("Иргэн", "Citizen"),
            }
            st.subheader("🎭 Тоглогчдын дүр" if mn else "🎭 Player roles")
            for player in players:
                if player.get("is_host"):
                    continue
                role = role_names.get(player.get("role"), ("Тоглогч", "Player"))[0 if mn else 1]
                st.write(f"• {player['name']}: {role}")

            if is_host:
                _render_mayor_night_report(
                    db, room_id, players,
                    int(room.get("round_number", 1)), lang,
                )
                if st.button("➕ Шинэ өрөө үүсгэх" if mn else "➕ Create a new room", key="new_room_after_game"):
                    try:
                        new_room, new_host = _create_mafia_room(db, current_player["name"])
                        st.session_state["mafia_room_id"] = new_room["id"]
                        st.session_state["mafia_player_id"] = new_host["id"]
                        st.rerun()
                    except Exception as exc:
                        st.error("Шинэ өрөө үүсгэж чадсангүй." if mn else "Could not create a new room.")
                        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                            st.code(f"{type(exc).__name__}: {exc}")
            else:
                st.info(
                    "Шинэ тоглолтод орохын тулд дууссан өрөөнөөс гараад Хотын даргын шинэ өрөөний кодоор нэгдэнэ үү."
                    if mn else "To play again, leave this finished room and join the Mayor's new room with its new code."
                )
                if st.button("Шинэ өрөөнд нэгдэх" if mn else "Join a new room", key="leave_finished_room"):
                    st.session_state.pop("mafia_room_id", None)
                    st.session_state.pop("mafia_player_id", None)
                    st.rerun()
        else:
            st.info(
                f"Тоглоомын үе: {phase}"
                if mn
                else f"Game phase: {phase}"
            )
        if st.button("Шинэчлэх" if mn else "Refresh", key="refresh_mafia_room"):
            st.rerun()

    except Exception as exc:
        st.error(
            "Өрөөний мэдээлэл авч чадсангүй."
            if mn
            else "Could not load the room."
        )
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _record_public_event(db, room_id: str, players: list[dict], body: str) -> None:
    host = next((p for p in players if p.get("is_host")), None)
    if not host:
        return
    try:
        db.table("game_messages").insert({
            "room_id": room_id,
            "player_id": host["id"],
            "body": f"📣 {body}",
        }).execute()
    except Exception:
        pass


def _clear_room_chat(db, room_id: str) -> None:
    """Keep chat scoped to the current game phase."""
    try:
        db.table("game_messages").delete().eq("room_id", room_id).execute()
    except Exception:
        pass


def _render_latest_public_event(db, room_id: str, players: list[dict]) -> None:
    host_ids = {p["id"] for p in players if p.get("is_host")}
    if not host_ids:
        return
    try:
        messages = (db.table("game_messages").select("player_id, body")
            .eq("room_id", room_id).order("created_at", desc=True)
            .limit(50).execute().data)
        event = next((m["body"] for m in messages
                      if m["player_id"] in host_ids
                      and m.get("body", "").startswith("📣 ")), None)
        if event:
            st.info(event[2:])
    except Exception:
        pass


def _render_day_chat_and_vote(
    db,
    room_id: str,
    player_id: str,
    players: list[dict],
    round_number: int,
    is_host: bool,
    lang: str,
) -> None:
    mn = lang == "mn"
    current_player = next(
        (player for player in players if player["id"] == player_id),
        None,
    )
    can_chat = bool(current_player and current_player.get("is_alive", True))

    st.subheader("💬 Өдрийн чат" if mn else "💬 Day chat")

    if not can_chat:
        st.info(
            "Та хасагдсан тул тоглоомыг ажиглаж болно, гэхдээ чат бичихгүй."
            if mn else "You are eliminated. You can spectate, but cannot send chat messages."
        )

    with st.form("mafia_chat_form", clear_on_submit=True):
        message = st.text_input(
            "Мессеж" if mn else "Message", disabled=not can_chat
        )
        send_message = st.form_submit_button(
            "Илгээх" if mn else "Send", disabled=not can_chat
        )

    if send_message and can_chat and message.strip():
        try:
            (
                db.table("game_messages")
                .insert({
                    "room_id": room_id,
                    "player_id": player_id,
                    "body": message.strip()[:500],
                })
                .execute()
            )
            st.rerun()
        except Exception as exc:
            st.error("Мессеж илгээж чадсангүй." if mn else "Could not send message.")
            with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                st.code(f"{type(exc).__name__}: {exc}")

    try:
        messages = (
            db.table("game_messages")
            .select("player_id, body, created_at")
            .eq("room_id", room_id)
            .order("created_at")
            .limit(50)
            .execute()
            .data
        )
        player_names = {
            player["id"]: (
                ("Хотын дарга" if mn else "Mayor")
                if player.get("is_host") else player["name"]
            )
            for player in players
        }

        if messages:
            for item in messages:
                sender = player_names.get(item["player_id"], "Player")
                st.write(f"**{sender}:** {item['body']}")
        else:
            st.caption("Одоогоор мессеж алга." if mn else "No messages yet.")

    except Exception as exc:
        st.error("Чат ачаалж чадсангүй." if mn else "Could not load chat.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")

    st.subheader("🗳️ Өдрийн санал" if mn else "🗳️ Day vote")

    alive_players = [
        player for player in players
        if player.get("is_alive", True) and not player.get("is_host")
    ]
    targets = [
        player for player in alive_players if player["id"] != player_id
    ]

    can_vote = bool(
        current_player
        and current_player.get("is_alive", True)
        and not current_player.get("is_host")
    )
    if not can_vote:
        st.info(
            "Хотын дарга санал өгөхгүй." if mn and is_host
            else "The Mayor does not vote." if is_host
            else "Та санал өгөх боломжгүй." if mn
            else "You cannot vote."
        )
    elif not targets:
        st.info(
            "Санал өгөх өөр тоглогч алга." if mn
            else "There are no other players to vote for."
        )
    else:
        target_names = {player["name"]: player["id"] for player in targets}

        with st.form("mafia_vote_form"):
            selected_name = st.selectbox(
                "Хэнийг саналд нэр дэвшүүлэх вэ?" if mn else "Who do you vote for?",
                list(target_names.keys()),
            )
            submit_vote = st.form_submit_button("Санал өгөх" if mn else "Submit vote")

        if submit_vote:
            try:
                existing = (
                    db.table("game_votes").select("id")
                    .eq("room_id", room_id).eq("round_number", round_number)
                    .eq("phase", "day").eq("voter_id", player_id)
                    .limit(1).execute().data
                )
                vote_data = {
                    "room_id": room_id, "round_number": round_number,
                    "phase": "day", "voter_id": player_id,
                    "target_id": target_names[selected_name],
                }
                if existing:
                    db.table("game_votes").update({
                        "target_id": target_names[selected_name]
                    }).eq("id", existing[0]["id"]).execute()
                else:
                    db.table("game_votes").insert(vote_data).execute()
                st.success("Санал хадгалагдлаа." if mn else "Vote saved.")
                st.rerun()
            except Exception as exc:
                st.error("Санал хадгалж чадсангүй." if mn else "Could not save vote.")
                with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                    st.code(f"{type(exc).__name__}: {exc}")

    try:
        votes = (
            db.table("game_votes")
            .select("voter_id, target_id")
            .eq("room_id", room_id)
            .eq("round_number", round_number)
            .eq("phase", "day")
            .execute()
            .data
        )
        alive_ids = {player["id"] for player in alive_players}
        votes = [
            vote for vote in votes
            if vote.get("voter_id") in alive_ids
            and vote.get("target_id") in alive_ids
        ]

        tally = {}
        for vote in votes:
            target_id = vote["target_id"]
            tally[target_id] = tally.get(target_id, 0) + 1

        st.caption(
            f"Санал өгсөн: {len(votes)} / {len(alive_players)}"
            if mn
            else f"Votes cast: {len(votes)} / {len(alive_players)}"
        )

        for target in alive_players:
            count = tally.get(target["id"], 0)
            st.write(f"• {target['name']}: {count}")

        if is_host:
            if len(votes) < len(alive_players):
                st.caption(
                    "Амьд тоглогч бүр санал өгсний дараа тооцоолно."
                    if mn else "Wait until every living player has voted."
                )
            elif st.button(
                "Санал тооцоолж, шөнө эхлүүлэх"
                if mn else "Resolve vote and start night",
                key=f"resolve_day_{round_number}",
            ):
                _resolve_day_vote(
                    db, room_id, votes, alive_players, players, mn
                )

    except Exception as exc:
        st.error("Саналын дүнг авч чадсангүй." if mn else "Could not load vote totals.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")



def _game_winner(players: list[dict]) -> str | None:
    alive = [p for p in players if p.get("is_alive", True) and not p.get("is_host")]
    mafia = sum(1 for p in alive if p.get("role") == "mafia")
    town = sum(1 for p in alive if p.get("role") in {"citizen", "doctor", "detective"})
    if mafia == 0:
        return "citizens"
    if mafia >= town:
        return "mafia"
    return None


def _resolve_day_vote(
    db, room_id: str, votes: list[dict],
    alive_players: list[dict], players: list[dict], mn: bool,
) -> None:
    alive_ids = {p["id"] for p in alive_players}
    valid = [
        v for v in votes
        if v.get("voter_id") in alive_ids and v.get("target_id") in alive_ids
    ]
    if len(valid) < len(alive_players):
        st.warning(
            "Амьд тоглогч бүр санал өгөөгүй байна."
            if mn else "Not every living player has voted yet."
        )
        return

    tally: dict[str, int] = {}
    for vote in valid:
        tally[vote["target_id"]] = tally.get(vote["target_id"], 0) + 1
    highest = max(tally.values(), default=0)
    leaders = [pid for pid, count in tally.items() if count == highest]
    eliminated = leaders[0] if highest and len(leaders) == 1 else None

    if eliminated:
        db.table("game_players").update({"is_alive": False}).eq(
            "id", eliminated
        ).execute()

    after = [
        {**p, "is_alive": False} if p["id"] == eliminated else p
        for p in players
    ]
    winner = _game_winner(after) if eliminated else None
    db.table("game_rooms").update({
        "phase": "finished" if winner else "night"
    }).eq("id", room_id).execute()

    player_names = {p["id"]: p["name"] for p in alive_players}
    tally_text = ", ".join(
        f"{player_names.get(p['id'], 'Player')}: {tally.get(p['id'], 0)}"
        for p in alive_players
    )
    if eliminated:
        eliminated_name = player_names.get(eliminated, "Player")
        event = (
            f"📊 Өдрийн саналын дүн — {tally_text}. {eliminated_name} олонхийн саналаар хасагдлаа. Шөнө эхэллээ."
            if mn else
            f"📊 Day vote results — {tally_text}. {eliminated_name} was eliminated by the vote. Night begins."
        )
    else:
        event = (
            f"📊 Өдрийн саналын дүн — {tally_text}. Санал тэнцсэн тул хэн ч хасагдсангүй. Шөнө эхэллээ."
            if mn else
            f"📊 Day vote results — {tally_text}. The vote was tied; nobody was eliminated. Night begins."
        )
    _clear_room_chat(db, room_id)
    _record_public_event(db, room_id, players, event)

    if eliminated:
        name = next((p["name"] for p in players if p["id"] == eliminated), "Player")
        if mn:
            outcome = (
                "Мафийн тал яллаа!" if winner == "mafia"
                else "Иргэд яллаа!" if winner == "citizens"
                else "Шөнө эхэллээ."
            )
            st.success(f"{name} хасагдлаа. {outcome}")
        else:
            outcome = (
                "The Mafia wins!" if winner == "mafia"
                else "The citizens win!" if winner == "citizens"
                else "Night begins."
            )
            st.success(f"{name} was eliminated. {outcome}")
    else:
        st.info(
            "Санал тэнцлээ. Хэн ч хасагдсангүй. Шөнө эхэллээ."
            if mn else "The vote is tied. Nobody was eliminated. Night begins."
        )
    st.rerun()


def _save_role_action(db, room_id: str, round_number: int, phase: str,
                     voter_id: str, target_id: str) -> None:
    existing = (
        db.table("game_votes").select("id")
        .eq("room_id", room_id).eq("round_number", round_number)
        .eq("phase", phase).eq("voter_id", voter_id)
        .limit(1).execute().data
    )
    if existing:
        db.table("game_votes").update({"target_id": target_id}).eq(
            "id", existing[0]["id"]
        ).execute()
    else:
        db.table("game_votes").insert({
            "room_id": room_id, "round_number": round_number,
            "phase": phase, "voter_id": voter_id, "target_id": target_id,
        }).execute()


def _render_detective_action(db, room_id: str, player_id: str,
                             players: list[dict], round_number: int,
                             lang: str) -> None:
    mn = lang == "mn"
    me = next((p for p in players if p["id"] == player_id), None)
    if not me or not me.get("is_alive", True) or me.get("role") != "detective":
        return

    st.subheader("🕵️ Цагдаагийн шалгалт" if mn else "🕵️ Detective check")
    st.caption(
        "Бүх тоглолтын турш нэг хүнийг л нууцаар шалгана. Өөрийгөө цагдаа гэж зарлахгүйгээр өдрийн чатаар бусдыг ятга."
        if mn else "You can secretly investigate only one player for the entire game. Persuade others in day chat without claiming to be the Detective."
    )
    alive = [p for p in players if p.get("is_alive", True) and p["id"] != player_id]
    if not alive:
        return
    actions = (db.table("game_votes").select("target_id, round_number")
        .eq("room_id", room_id)
        .eq("phase", "night").eq("voter_id", player_id)
        .limit(1).execute().data)
    if actions:
        target = next((p for p in players if p["id"] == actions[0]["target_id"]), None)
        if target:
            is_mafia = target.get("role") == "mafia"
            result = ("Мафийн тал" if is_mafia else "Мафийн тал биш") if mn else ("Mafia" if is_mafia else "Not Mafia")
            st.success(f"{target['name']}: {result}")
        st.caption(
            "Энэ тоглолтын ганц шалгалтаа ашигласан. Өдрийн чатаар бусдыг ятгаж болно."
            if mn else "You used your one investigation for this game. Use day chat to persuade the others."
        )
        return

    choices = {p["name"]: p["id"] for p in alive}
    with st.form(f"detective_{round_number}"):
        selected = st.selectbox("Хэнийг шалгах вэ?" if mn else "Who do you investigate?", list(choices))
        submit = st.form_submit_button("Нууцаар шалгах" if mn else "Investigate privately")
    if submit:
        try:
            _save_role_action(db, room_id, round_number, "night", player_id, choices[selected])
            st.rerun()
        except Exception as exc:
            st.error("Шалгалтыг хадгалж чадсангүй." if mn else "Could not save investigation.")
            with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                st.code(f"{type(exc).__name__}: {exc}")


def _render_night(db, room_id: str, player_id: str, players: list[dict],
                  round_number: int, is_host: bool, lang: str) -> None:
    mn = lang == "mn"
    alive = [p for p in players if p.get("is_alive", True) and not p.get("is_host")]
    mafia = [p for p in alive if p.get("role") == "mafia"]
    doctors = [p for p in alive if p.get("role") == "doctor"]
    targets = [p for p in alive if p.get("role") != "mafia"]
    me = next((p for p in players if p["id"] == player_id), None)

    if me and me.get("is_alive", True) and me.get("role") == "mafia" and targets:
        st.subheader("🌙 Мафийн сонголт" if mn else "🌙 Mafia action")
        choices = {p["name"]: p["id"] for p in targets}
        with st.form(f"mafia_night_{round_number}"):
            selected = st.selectbox("Хэнийг онилох вэ?" if mn else "Choose a target", list(choices))
            send = st.form_submit_button("Сонголт хийх" if mn else "Choose target")
        if send:
            try:
                _save_role_action(db, room_id, round_number, "night", player_id, choices[selected])
                st.rerun()
            except Exception as exc:
                st.error("Шөнийн сонголтыг хадгалж чадсангүй." if mn else "Could not save night choice.")
                with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                    st.code(f"{type(exc).__name__}: {exc}")

    if me and me.get("is_alive", True) and me.get("role") == "doctor":
        st.subheader("🛡️ Эмчийн сонголт" if mn else "🛡️ Doctor action")
        st.caption("Эмч нэг тоглогчийг хамгаална." if mn else "Choose one player to protect.")
        _render_doctor_plant_context(lang, round_number)
        heal_choices = {p["name"]: p["id"] for p in alive}
        with st.form(f"doctor_night_{round_number}"):
            selected_heal = st.selectbox("Хэнийг эмчлэх вэ?" if mn else "Who do you protect?", list(heal_choices))
            heal = st.form_submit_button("Хамгаалах" if mn else "Protect")
        if heal:
            try:
                _save_role_action(db, room_id, round_number, "night", player_id, heal_choices[selected_heal])
                st.rerun()
            except Exception as exc:
                st.error("Эмчийн сонголтыг хадгалж чадсангүй." if mn else "Could not save doctor action.")
                with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                    st.code(f"{type(exc).__name__}: {exc}")

    if me and me.get("is_alive", True) and not me.get("is_host") and me.get("role") not in ("mafia", "doctor"):
        st.info("Шөнө болж байна. Мафийн үйлдлийг хүлээнэ үү." if mn else "It is night. Wait for the Mafia action.")
    elif me and not me.get("is_alive", True):
        st.info("Та хасагдсан. Шөнийн үр дүнг хүлээнэ үү." if mn else "You are eliminated. Wait for the night result.")

    try:
        actions = db.table("game_votes").select("voter_id, target_id").eq(
            "room_id", room_id
        ).eq("round_number", round_number).eq("phase", "night").execute().data
        mafia_ids = {p["id"] for p in mafia}
        doctor_ids = {p["id"] for p in doctors}
        target_ids = {p["id"] for p in targets}
        mafia_votes = [v for v in actions if v["voter_id"] in mafia_ids and v["target_id"] in target_ids]
        doctor_votes = [v for v in actions if v["voter_id"] in doctor_ids]
        if is_host:
            if mafia_votes or doctor_votes:
                with st.expander("Хотын даргын нууц самбар" if mn else "Mayor's private control panel"):
                    player_names = {p["id"]: p["name"] for p in players}
                    mafia_tally = {}
                    for vote in mafia_votes:
                        mafia_tally[vote["target_id"]] = mafia_tally.get(vote["target_id"], 0) + 1
                    highest = max(mafia_tally.values(), default=0)
                    leaders = [pid for pid, count in mafia_tally.items() if count == highest]
                    mafia_target = leaders[0] if highest and len(leaders) == 1 else None
                    doctor_targets = {v["target_id"] for v in doctor_votes}
                    if mafia_target:
                        st.write(("Мафийн онилсон хүн: " if mn else "Mafia target: ") + player_names.get(mafia_target, "—"))
                    elif mafia_tally:
                        st.info("Мафийн санал тэнцсэн байна." if mn else "The Mafia vote is tied.")
                    for target_id in sorted(doctor_targets):
                        st.write(("Эмчийн хамгаалсан хүн: " if mn else "Doctor protected: ") + player_names.get(target_id, "—"))
                    if mafia_target and mafia_target in doctor_targets:
                        st.success("Эмч мафийн онилсон хүнийг аварна." if mn else "The Doctor protects the Mafia's target.")
            ready = len(mafia_votes) >= len(mafia) and len(doctor_votes) >= len(doctors)
            if not ready:
                st.caption("Мафийнхан болон амьд эмч сонголтоо хийсний дараа шөнийг дуусгана." if mn else "Wait for the living Mafia and Doctor to submit their actions.")
            elif st.button("Шөнийг дуусгах" if mn else "Resolve night", key=f"resolve_night_{round_number}"):
                _resolve_night(db, room_id, round_number, mafia_votes, doctor_votes, players, mn)
        elif me and me.get("is_host"):
            st.caption("Хүлээнэ үү." if mn else "Waiting.")
        else:
            st.caption("Өрөөний эзэн шөнийн үр дүнг баталгаажуулна." if mn else "The host will resolve the night.")
    except Exception as exc:
        st.error("Шөнийн сонголтыг уншиж чадсангүй." if mn else "Could not load night actions.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _resolve_night(db, room_id: str, round_number: int, mafia_votes: list[dict],
                   doctor_votes: list[dict], players: list[dict], mn: bool) -> None:
    tally: dict[str, int] = {}
    for vote in mafia_votes:
        tally[vote["target_id"]] = tally.get(vote["target_id"], 0) + 1
    highest = max(tally.values(), default=0)
    leaders = [pid for pid, count in tally.items() if count == highest]
    mafia_target = leaders[0] if highest and len(leaders) == 1 else None
    protected = doctor_votes[0]["target_id"] if doctor_votes else None
    eliminated = mafia_target if mafia_target and mafia_target != protected else None

    if eliminated:
        db.table("game_players").update({"is_alive": False}).eq("id", eliminated).execute()
    after = [{**p, "is_alive": False} if p["id"] == eliminated else p for p in players]
    winner = _game_winner(after)
    updates = {"phase": "finished" if winner else "day"}
    if not winner:
        updates["round_number"] = round_number + 1
    db.table("game_rooms").update(updates).eq("id", room_id).execute()

    victim_name = next((p["name"] for p in players if p["id"] == eliminated), "Тоглогч" if mn else "A player")
    if eliminated:
        public_text = (
            f"🌅 Өглөө боллоо. {victim_name} шөнө нас барлаа. Эмч өөр хүнийг хамгаалсан тул аварч чадсангүй."
            if mn and protected else
            f"🌅 Өглөө боллоо. {victim_name} шөнө нас барлаа. Эмч энэ шөнө хамгаалж чадсангүй."
            if mn else
            f"🌅 Morning. {victim_name} died overnight. The Doctor protected someone else and could not save them."
            if protected else
            f"🌅 Morning. {victim_name} died overnight. The Doctor did not protect them."
        )
    elif mafia_target and mafia_target == protected:
        public_text = (
            "🌅 Өглөө боллоо. Энэ шөнө хүн нас барсангүй. Эмч мафийн онилсон хүнийг аварлаа."
            if mn else
            "🌅 Morning. Nobody died. The Doctor saved the Mafia's target."
        )
    else:
        public_text = (
            "🌅 Өглөө боллоо. Мафийн санал тэнцсэн тул хүн нас барсангүй."
            if mn else
            "🌅 Morning. The Mafia vote was tied, so nobody died."
        )
    _clear_room_chat(db, room_id)
    _record_public_event(db, room_id, players, public_text)

    if eliminated:
        name = next((p["name"] for p in players if p["id"] == eliminated), "Player")
        text = f"Шөнө {name} хасагдлаа." if mn else f"{name} was eliminated at night."
        st.info(text + (" Мафийн тал яллаа!" if mn and winner == "mafia" else " Иргэд яллаа!" if mn and winner == "citizens" else " Өдөр эхэллээ." if mn else " The Mafia wins!" if winner == "mafia" else " The citizens win!" if winner == "citizens" else " Day begins."))
    elif mafia_target and mafia_target == protected:
        st.success("Эмч онилсон тоглогчоо аварлаа. Өдөр эхэллээ." if mn else "The Doctor protected the targeted player. Day begins.")
    else:
        st.info("Шөнийн санал тэнцлээ. Хэн ч хасагдсангүй. Өдөр эхэллээ." if mn else "The Mafia vote tied. Nobody was eliminated. Day begins.")
    st.rerun()



def _render_mayor_night_report(db, room_id: str, players: list[dict],
                               round_number: int, lang: str) -> None:
    mn = lang == "mn"
    try:
        actions = []
        for candidate_round in (round_number, round_number - 1):
            if candidate_round < 1:
                continue
            actions = (db.table("game_votes").select("voter_id, target_id")
                .eq("room_id", room_id).eq("round_number", candidate_round)
                .eq("phase", "night").execute().data)
            if actions:
                break
        if not actions:
            return
        names = {p["id"]: p["name"] for p in players}
        mafia_ids = {p["id"] for p in players if p.get("role") == "mafia" and not p.get("is_host")}
        doctor_ids = {p["id"] for p in players if p.get("role") == "doctor" and not p.get("is_host")}
        mafia_tally = {}
        for vote in actions:
            if vote["voter_id"] in mafia_ids:
                mafia_tally[vote["target_id"]] = mafia_tally.get(vote["target_id"], 0) + 1
        highest = max(mafia_tally.values(), default=0)
        leaders = [pid for pid, count in mafia_tally.items() if count == highest]
        mafia_target = leaders[0] if highest and len(leaders) == 1 else None
        doctor_targets = {v["target_id"] for v in actions if v["voter_id"] in doctor_ids}
        with st.expander("Хотын даргын нууц тайлан" if mn else "Mayor's private night report"):
            if mafia_target:
                st.write(("Мафийн онилсон хүн: " if mn else "Mafia target: ") + names.get(mafia_target, "—"))
            elif mafia_tally:
                st.info("Мафийн санал тэнцсэн." if mn else "The Mafia vote was tied.")
            for target_id in sorted(doctor_targets):
                st.write(("Эмчийн хамгаалсан хүн: " if mn else "Doctor protected: ") + names.get(target_id, "—"))
            if mafia_target and mafia_target in doctor_targets:
                st.success("Эмч мафийн онилсон хүнийг аварсан." if mn else "The Doctor saved the Mafia's target.")
            elif mafia_target:
                st.info("Эмч мафийн онилсон хүнийг хамгаалаагүй." if mn else "The Doctor did not protect the Mafia's target.")
    except Exception as exc:
        st.caption(("Нууц тайлан ачаалж чадсангүй: " if mn else "Could not load private report: ") + str(exc))

def _create_mafia_room(db, host_name: str) -> tuple[dict, dict]:
    code = "".join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(6)
    )
    room = (
        db.table("game_rooms")
        .insert({
            "code": code,
            "phase": "lobby",
            "round_number": 0,
            "host_name": host_name,
        })
        .execute()
        .data[0]
    )
    host = (
        db.table("game_players")
        .insert({
            "room_id": room["id"],
            "name": host_name,
            "role": None,
            "is_alive": True,
            "is_host": True,
        })
        .execute()
        .data[0]
    )
    return room, host


def _render_create_join(db, lang: str) -> None:
    mn = lang == "mn"

    with st.form("create_mafia_room"):
        host_name = st.text_input("Таны нэр" if mn else "Your name")
        create_clicked = st.form_submit_button(
            "Өрөө үүсгэх" if mn else "Create room"
        )

    if create_clicked:
        host_name = host_name.strip()
        if not host_name:
            st.warning("Нэрээ оруулна уу." if mn else "Enter your name.")
        else:
            try:
                room, player = _create_mafia_room(db, host_name)

                st.session_state["mafia_room_id"] = room["id"]
                st.session_state["mafia_player_id"] = player["id"]
                st.rerun()

            except Exception as exc:
                st.error("Өрөө үүсгэж чадсангүй." if mn else "Could not create room.")
                with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                    st.code(f"{type(exc).__name__}: {exc}")

    st.divider()

    with st.form("join_mafia_room"):
        player_name = st.text_input("Таны нэр" if mn else "Your name")
        room_code = st.text_input("Өрөөний код" if mn else "Room code")
        join_clicked = st.form_submit_button("Нэгдэх" if mn else "Join room")

    if join_clicked:
        player_name = player_name.strip()
        room_code = room_code.strip().upper()

        if not player_name or not room_code:
            st.warning(
                "Нэр болон өрөөний кодоо оруулна уу."
                if mn
                else "Enter your name and room code."
            )
            return

        try:
            rooms = (
                db.table("game_rooms")
                .select("id, code, phase")
                .eq("code", room_code)
                .limit(1)
                .execute()
                .data
            )

            if not rooms:
                st.error("Ийм кодтой өрөө олдсонгүй." if mn else "Room code not found.")
                return

            room = rooms[0]
            if room["phase"] != "lobby":
                st.error(
                    "Энэ өрөө тоглоомоо эхлүүлсэн байна."
                    if mn
                    else "Game already started."
                )
                return

            players = (
                db.table("game_players")
                .select("id, is_host")
                .eq("room_id", room["id"])
                .execute()
                .data
            )

            participant_count = sum(1 for p in players if not p.get("is_host"))
            if participant_count >= ROOM_CAPACITY:
                st.error(
                    "Өрөө дүүрсэн байна (12 тоглогч)."
                    if mn
                    else "Room is full (12 players)."
                )
                return

            player = (
                db.table("game_players")
                .insert({
                    "room_id": room["id"],
                    "name": player_name,
                    "role": None,
                    "is_alive": True,
                    "is_host": False,
                })
                .execute()
                .data[0]
            )

            st.session_state["mafia_room_id"] = room["id"]
            st.session_state["mafia_player_id"] = player["id"]
            st.rerun()

        except Exception as exc:
            st.error("Өрөөнд нэгдэж чадсангүй." if mn else "Could not join room.")
            with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                st.code(f"{type(exc).__name__}: {exc}")
