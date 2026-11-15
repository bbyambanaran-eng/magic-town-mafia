import secrets
import string
import random
import html
import base64
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from .supabase_client import get_supabase_client
from .weather import fetch_weather, weather_label

ROOM_CAPACITY = 12
PRESENCE_TIMEOUT_SECONDS = 120
ASSET_DIR = Path(__file__).parent / "assets"
PUBLIC_CHARACTER_PORTRAITS = (
    "characters/citizen_male.webp",
    "characters/citizen_female.webp",
)


def _render_player_seats(
    players: list[dict], room_id: str, lang: str, phase: str,
    db=None, viewer: dict | None = None, round_number: int = 1,
) -> None:
    """Show public character portraits assigned independently from secret roles."""
    contestants = [player for player in players if not player.get("is_host")]
    if phase == "day":
        _render_day_vote_cards(
            db, room_id, contestants, viewer, round_number, lang
        )
        return

    # Seat portraits are role-neutral while the game is active. Reveal the real
    # role portrait only after the room is finished; never leak roles mid-game.
    finished = phase == "finished"
    cells = []
    for index, player in enumerate(contestants[:ROOM_CAPACITY]):
        role = player.get("role") if finished else None
        if role:
            portrait_path = _private_role_portrait(str(role), str(player["id"]))
        else:
            portrait_path = random.Random(
                f"public-portrait:{room_id}:{player['id']}"
            ).choice(PUBLIC_CHARACTER_PORTRAITS)
        portrait = _brand_asset(portrait_path)
        image_type = "image/png" if portrait_path.endswith(".png") else "image/webp"
        anonymous_label = f"Тоглогч {index + 1}" if lang == "mn" else f"Player {index + 1}"
        public_name = player.get("name") or anonymous_label
        seat_label = html.escape(str(public_name))
        role_labels = {
            "mafia": ("Мафийн тал", "Mafia"),
            "doctor": ("Эмч", "Doctor"),
            "detective": ("Цагдаа", "Detective"),
            "citizen": ("Иргэн", "Citizen"),
        }
        role_label = role_labels.get(role, ("", ""))[0 if lang == "mn" else 1]
        if player.get("is_observer"):
            status = "Ажиглагч" if lang == "mn" else "Spectating"
        elif not player.get("is_alive", True):
            status = "Хасагдсан" if lang == "mn" else "Eliminated"
        elif phase == "lobby":
            status = "Бэлэн" if lang == "mn" else "Ready"
        else:
            status = "Тоглож байна" if lang == "mn" else "Playing"
        cells.append(
            f'<article class="mt-seat">'
            f'<img src="data:{image_type};base64,{portrait}" alt="Character portrait" />'
            f'<div class="mt-seat-name">{seat_label}</div>'
            f'<div class="mt-seat-role">{html.escape(role_label)}</div>'
            f'<div class="mt-seat-status">{status}</div></article>'
        )
    if phase == "lobby":
        for seat_number in range(len(contestants), ROOM_CAPACITY):
            waiting = "Хүлээж байна" if lang == "mn" else "Waiting for player"
            cells.append(
                '<article class="mt-seat mt-seat-empty">'
                f'<div>{waiting}<br><small>{seat_number + 1} / {ROOM_CAPACITY}</small></div>'
                '</article>'
            )
    st.markdown(
        """
        <style>
        .mt-seat-board{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));
            gap:.8rem;margin:.65rem 0 1.1rem;padding:1rem;border:1px solid #d9b65e66;
            border-radius:18px;background:linear-gradient(145deg,rgba(10,20,35,.94),rgba(22,35,52,.94));
            box-shadow:0 14px 34px #0005;}
        .mt-seat{min-width:0;overflow:hidden;text-align:center;border:1px solid #cba95c99;
            border-radius:15px;background:linear-gradient(180deg,#172338,#0d1726);
            box-shadow:0 7px 20px #0005;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease;}
        .mt-seat:hover{transform:translateY(-3px);border-color:#f0d58f;box-shadow:0 12px 26px #0008,0 0 18px #d9b65e22;}
        .mt-seat img{display:block;width:100%;height:100px;padding:.35rem;
            box-sizing:border-box;object-fit:contain;object-position:center;background:#0a1422;}
        .mt-seat-name{padding:.5rem .35rem 0;color:#fff1c4;font-weight:750;overflow-wrap:anywhere;}
        .mt-seat-role{min-height:1.2em;padding:.15rem .3rem 0;color:#e8c86f;font-weight:700;}
        .mt-seat-status{padding:.12rem .3rem .55rem;color:#d7e0eb;font-size:.78rem;}
        .mt-seat-empty{min-height:76px;display:flex;align-items:center;justify-content:center;
            border-style:dashed;opacity:.52;box-shadow:none;}
        .mt-seat-empty small{font-size:.76rem;}
        .mt-lobby-seat-board{gap:.45rem;margin:.3rem 0;padding:.6rem;}
        @media(max-width:1000px){.mt-seat-board{grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;padding:.75rem;}}
        @media(max-width:700px){.mt-seat-board{grid-template-columns:repeat(2,minmax(0,1fr));}
            .mt-seat-empty{min-height:104px;}}
        @media(max-width:420px){.mt-seat-board{grid-template-columns:repeat(2,minmax(0,1fr));padding:.55rem;gap:.4rem;}
            .mt-seat img{height:84px}}
        </style>
        """
            + f'<section class="mt-seat-board{" mt-lobby-seat-board" if phase == "lobby" else ""}">'
        + "".join(cells)
        + "</section>",
        unsafe_allow_html=True,
    )


def _render_day_vote_cards(
    db, room_id: str, contestants: list[dict], viewer: dict | None,
    round_number: int, lang: str,
) -> None:
    """Render role-neutral character cards with a vote action on each eligible card."""
    mn = lang == "mn"
    can_vote = bool(
        db is not None
        and viewer
        and not viewer.get("is_host")
        and viewer.get("is_alive", True)
        and not viewer.get("is_observer")
    )
    my_vote_target = None
    if can_vote:
        try:
            current_vote = (
                db.table("game_votes")
                .select("target_id")
                .eq("room_id", room_id)
                .eq("round_number", round_number)
                .eq("phase", "day")
                .eq("voter_id", viewer["id"])
                .limit(1)
                .execute()
                .data
            )
            if current_vote:
                my_vote_target = current_vote[0].get("target_id")
        except Exception:
            my_vote_target = None
    columns = st.columns(6, vertical_alignment="top")
    for index, player in enumerate(contestants[:ROOM_CAPACITY]):
        with columns[index % len(columns)]:
            with st.container(border=True):
                portrait_path = random.Random(
                    f"public-portrait:{room_id}:{player['id']}"
                ).choice(PUBLIC_CHARACTER_PORTRAITS)
                st.image(
                    ASSET_DIR / portrait_path,
                    width=64,
                    alt="Citizen portrait",
                )
                st.markdown(f"**{player.get('name') or ('Player ' + str(index + 1))}**")
                if player.get("is_observer") or not player.get("is_alive", True):
                    status = "Ажиглагч" if mn else "Spectating"
                    st.caption(status)

                is_target = (
                    player.get("is_alive", True)
                    and not player.get("is_observer")
                    and player.get("id") != (viewer or {}).get("id")
                )
                if can_vote and is_target:
                    already_selected = str(player["id"]) == str(my_vote_target)
                    if st.button(
                        (
                            "✅ Сонгосон" if already_selected else "🗳️ Санал"
                        ) if mn else (
                            "✅ Voted" if already_selected else "🗳️ Vote"
                        ),
                        key=f"vote_card_{round_number}_{viewer['id']}_{player['id']}",
                        width="stretch",
                        type="primary" if already_selected else "secondary",
                    ):
                        try:
                            _cast_day_vote(
                                db, room_id, round_number,
                                str(viewer["id"]), str(player["id"]),
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error("Санал хадгалж чадсангүй." if mn else "Could not save vote.")
                            with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                                st.code(f"{type(exc).__name__}: {exc}")


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


def _render_brand_banner(lang: str, compact: bool = False) -> None:
    mn = lang == "mn"
    logo = _brand_asset("aum_shield.png")
    skyline = _brand_asset("ulaanbaatar_skyline.svg")
    mafia = _brand_asset("characters/mafia.webp")
    st.markdown(
        f"""
        <style>
        .magic-town-hero {{
            position: relative; isolation: isolate; overflow: hidden;
            min-height: 150px; margin: 0 0 .45rem; padding: .8rem 1rem;
            display: grid; grid-template-columns: 1fr; align-items: center;
            border: 1px solid rgba(225,190,103,.42); border-radius: 18px;
            background: linear-gradient(90deg,rgba(7,16,31,.98) 0%,rgba(7,16,31,.9) 52%,rgba(7,16,31,.56) 100%),
                url(data:image/webp;base64,{mafia}) right 1rem center / auto 150px no-repeat,
                linear-gradient(110deg,rgba(7,16,31,.97),rgba(17,31,52,.79) 52%,rgba(7,16,31,.96));
            box-shadow: 0 14px 38px rgba(0,0,0,.2);
        }}
        .magic-town-hero .magic-skyline {{
            position: absolute; inset: auto 0 0; width: 100%; height: 132px;
            object-fit: cover; object-position: center bottom; opacity: .58; z-index: -1;
        }}
        .magic-town-brand {{ color:#f0d182 !important; font-size:clamp(1.7rem,4vw,2.5rem); font-weight:800; text-align:center; text-shadow:0 2px 14px #000; }}
        .magic-town-kicker {{ max-width:48rem; margin:.25rem auto 0; color:#e4eaf1 !important; font-size:.98rem; text-align:center; text-shadow:0 2px 10px #000; }}
        .magic-town-emblem {{
            position:absolute; top:.65rem; left:1rem; width:48px; height:48px; padding:5px; box-sizing:border-box;
            border-radius:50%; background:radial-gradient(circle,#fff9df 0 48%,#d9b65e 52%,#80652c 66%,transparent 71%);
            box-shadow:0 0 28px #e8c55e66; display:flex; align-items:center; justify-content:center;
        }}
        .magic-town-emblem img {{ width:34px; height:38px; object-fit:contain; border-radius:7px; box-shadow:0 0 0 2px #e4c369; }}
        .magic-town-hero.compact {{ min-height:44px; height:44px; padding:.15rem .7rem; margin-bottom:.35rem; border-radius:12px;
            background:linear-gradient(110deg,rgba(7,16,31,.97),rgba(17,31,52,.9)); }}
        .magic-town-hero.compact .magic-town-brand {{ font-size:1.12rem; line-height:1.25; }}
        .magic-town-hero.compact .magic-town-kicker {{ display:none; }}
        .magic-town-hero.compact .magic-town-emblem {{ top:.3rem; left:.5rem; width:32px; height:32px; padding:3px; }}
        .magic-town-hero.compact .magic-town-emblem img {{ width:21px; height:24px; }}
        [data-testid="stMain"] > div {{ padding-top: .25rem; }}
        [data-testid="stMainBlockContainer"] {{ padding-top:.25rem !important; padding-bottom:.2rem !important; }}
        [data-testid="stMain"] [data-testid="stVerticalBlock"] {{ gap:.28rem !important; }}
        [data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3 {{ margin-bottom:.15rem !important; }}
        [data-testid="stMain"] [data-testid="stMarkdownContainer"] p {{ margin-bottom:.3rem !important; }}
        [data-testid="stMain"] [data-testid="stCaptionContainer"] {{ margin-bottom:0 !important; }}
        [data-testid="stMain"] [data-testid="stImage"] {{ margin-bottom:0 !important; }}
        [data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3 {{ letter-spacing:.01em; }}
        [data-testid="stMain"] [data-testid="stCaptionContainer"] {{ color:#c5ced9 !important; }}
        [data-testid="stMain"] [data-testid="stAlert"] {{ border-radius:12px; }}
        [data-testid="stMain"] .stButton > button {{ border-radius:10px; min-height:2.55rem; }}
        @media (max-width:620px) {{
            .magic-town-hero {{ min-height:132px; padding:2.7rem .85rem .8rem; background-size:auto, auto 125px, auto; }}
            .magic-town-emblem {{ top:.55rem; left:.65rem; width:38px; height:38px; }}
            .magic-town-emblem img {{ width:26px; height:30px; }}
        }}
        </style>
        <section class="magic-town-hero{' compact' if compact else ''}">
            <img class="magic-skyline" src="data:image/svg+xml;base64,{skyline}" alt="Ulaanbaatar skyline at night" />
            <div>
                <div class="magic-town-brand">🌙 Magic Town Mafia</div>
                <div class="magic-town-kicker">{"Мафиаг олж, хотоо авраарай." if mn else "Find the Mafia. Save the town."}</div>
            </div>
            <div class="magic-town-emblem"><img src="data:image/png;base64,{logo}" alt="American University of Mongolia shield" /></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=900, show_spinner=False)
def _game_weather(day_key: str) -> dict:
    # Include Ulaanbaatar local date in the cache key so midnight starts a fresh fetch.
    return fetch_weather()


def _render_real_world_context(lang: str, game_phase: str) -> None:
    mn = lang == "mn"
    _render_real_world_weather(lang, game_phase, mn)


def _render_real_world_weather(lang: str, game_phase: str, mn: bool) -> None:
    local_zone = ZoneInfo("Asia/Ulaanbaatar")
    now_local = datetime.now(local_zone).replace(tzinfo=None)
    today_key = now_local.date().isoformat()
    # Set the phase theme before requesting live data so an API timeout cannot
    # leave the previous phase's background on screen.
    is_daylight = game_phase == "day" if game_phase in {"day", "night"} else None
    _apply_weather_theme(is_daylight, None, None, None)
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
        # In a live game, follow the Mayor-controlled phase; in the lobby or
        # after the game, follow Open-Meteo's actual local daylight.
        report_time = datetime.fromisoformat(current["time"]).time()
        sunrise = datetime.fromisoformat(today["sunrise"]).time()
        sunset = datetime.fromisoformat(today["sunset"]).time()
        actual_daylight = sunrise <= report_time < sunset
        if is_daylight is None:
            is_daylight = actual_daylight
        weather_code = int(current["weather_code"])
        wind_speed = current.get("wind_speed")
        cloud_cover = current.get("cloud_pct")
        _apply_weather_theme(
            is_daylight,
            weather_code,
            wind_speed if isinstance(wind_speed, (int, float)) else None,
            cloud_cover if isinstance(cloud_cover, (int, float)) else None,
        )

        game_sky = (
            ("☀️ Тоглоомын өдөр" if is_daylight else "🌙 Тоглоомын шөнө")
            if mn else ("☀️ Game day" if is_daylight else "🌙 Game night")
        )
        actual_sky = (
            ("☀️ УБ-д өдөр" if actual_daylight else "🌙 УБ-д шөнө")
            if mn else ("☀️ Ulaanbaatar: day" if actual_daylight else "🌙 Ulaanbaatar: night")
        )
        sky = (
            f"{game_sky} · {actual_sky}"
            if game_phase in {"day", "night"}
            else actual_sky
        )
        condition = weather_label(weather_code, lang)
        temp = current.get("temperature_c")
        temp_text = f"{temp:.1f} °C" if isinstance(temp, (int, float)) else "—"
        wind_text = f"{wind_speed:.1f} m/s" if isinstance(wind_speed, (int, float)) else "—"
        data_label = "Бодит" if mn else "Live"
        st.caption(f"🌦️ {data_label} · {temp_text} · {condition} · 💨 {wind_text} · {sky}")
    except Exception:
        st.info(
            "Цаг агаарын бодит дата алга тул цаг агаарын нөхцөл харуулахгүй. Тоглоом хэвийн үргэлжилнэ."
            if mn else
            "Live weather is unavailable, so no weather condition is shown. The game continues."
        )


def _apply_weather_theme(
    is_daylight: bool | None,
    weather_code: int | None,
    wind_speed: float | None,
    cloud_cover: float | None,
) -> None:
    snow_codes = {71, 73, 75, 77, 85, 86}
    rain_codes = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    cloud_codes = {2, 3, 45, 48}
    is_snowing = weather_code in snow_codes if weather_code is not None else False
    is_raining = weather_code in rain_codes if weather_code is not None else False
    is_windy = wind_speed is not None and wind_speed >= 8.0
    is_cloudy = (
        (weather_code in cloud_codes if weather_code is not None else False)
        or (cloud_cover is not None and cloud_cover >= 75)
    )

    if is_daylight is None:
        celestial = ""
        sky = "linear-gradient(180deg, #344052 0%, #475365 52%, #303b4a 100%)"
    elif is_daylight:
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
        """ if is_daylight is False else ""

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
        [data-testid="stMain"] {
            font-family: "Segoe UI", Arial, sans-serif !important;
            font-size: 1rem !important;
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
        [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: .65rem .75rem !important;
        }
        [data-testid="stMain"] [data-testid="stColumn"] [data-testid="stImage"] img {
            max-height: 120px !important;
            object-fit: contain !important;
        }
        [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] strong {
            font-size: 1.12rem !important;
            line-height: 1.3 !important;
        }
        [data-testid="stMain"] .stButton > button {
            min-height: 2.55rem !important;
            padding: .35rem .65rem !important;
            font-size: 1rem !important;
            font-weight: 650 !important;
        }
        [data-testid="stMain"] [data-testid="stCaptionContainer"],
        [data-testid="stMain"] [data-testid="stWidgetLabel"] label {
            color: #fff7e5 !important;
            font-size: 1rem !important;
            font-weight: 600 !important;
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
        [data-testid="stMain"] button[data-testid="stBaseButton-primary"] {
            color: #102719 !important;
            border-color: #a9e4b6 !important;
            background: linear-gradient(180deg, #b9edc3, #66bd7d) !important;
        }
        [data-testid="stMain"] button:hover,
        [data-testid="stMain"] [role="button"]:hover {
            border-color: #fff0bd !important;
            background: linear-gradient(180deg, #ffe7a5, #d5ad5d) !important;
        }
        [data-testid="stMain"] button[data-testid="stBaseButton-primary"]:hover {
            border-color: #d4f7dc !important;
            background: linear-gradient(180deg, #c9f3d0, #78cc8c) !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #101b2c, #111827) !important;
            border-right: 1px solid rgba(226,190,103,.42) !important;
        }
    """

    navy_overlay = (
        "linear-gradient(180deg, rgba(12,21,37,.58), rgba(12,20,35,.72))"
        if is_daylight else
        "linear-gradient(180deg, rgba(8,15,29,.82), rgba(8,14,26,.90))"
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


@st.fragment(run_every="10s")
def render_game_lobby(lang: str) -> None:
    mn = lang == "mn"
    room_id = st.session_state.get("mafia_room_id")
    _render_brand_banner(lang, compact=bool(room_id))

    try:
        db = get_supabase_client()
    except Exception as exc:
        st.error("Supabase холболт амжилтгүй." if mn else "Supabase connection failed.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")
        return

    player_id = st.session_state.get("mafia_player_id")

    if room_id:
        _render_current_room(db, room_id, player_id, lang)
        return

    _render_real_world_context(lang, "lobby")
    _render_create_join(db, lang)
    _render_home_steps(lang)


def _render_home_steps(lang: str) -> None:
    mn = lang == "mn"
    title = "Тоглох дүрэм · Нууцлал" if mn else "How to play · Rules & privacy"
    with st.expander(title):
        st.markdown("**Раундын дараалал**" if mn else "**Round flow**")
        st.caption(
            "Дүрүүд: Энгийн иргэн · Эмч · Цагдаа · Мафи"
            if mn else "Roles: Citizen · Doctor · Detective · Mafia"
        )
        st.markdown(
            "- **Шөнө:** Мафи хувийн чатаар ярилцаж байг сонгоно; эмч хамгаалж, цагдаа нэг удаа нууцаар шалгана."
            "\n- **Өдөр:** Амьд тоглогчид ярилцаж, санал өгнө. Хотын дарга тоглогч биш; үйлдлүүд бэлэн бол үеийг шилжүүлнэ. Цагийн хязгааргүй."
            "\n- **Ялалт:** Бүх мафи хасагдвал иргэд ялна. Энгийн иргэн үлдэхгүй бол эмч, цагдаа амьд байсан ч мафи ялна."
            "\n- **Нууц дүрүүд:** Тоглогч зөвхөн өөрийн дүрийг харна. Бусдын дүр, эцсийн үр дүн тоглоом дуусахад ил болно."
            "\n- **Ажиглагч:** Хасагдсан эсвэл салсан тоглогч ажиглагч болж, тоглоом үргэлжилнэ."
            if mn else
            "- **Night:** Mafia coordinate in private and choose a target; the Doctor protects, and the Detective gets one secret check."
            "\n- **Day:** Living players discuss and vote. The non-playing Mayor advances the phase after actions are ready. There is no timer."
            "\n- **Win:** The Town wins when all Mafia are out. Mafia wins when no Citizen remains, even if the Doctor or Detective is alive."
            "\n- **Secret roles:** Each player sees only their own role. Everyone's role and the result are revealed after the game ends."
            "\n- **Observers:** Eliminated or disconnected players become observers; the game continues."
        )
        st.markdown("**Цаг агаар**" if mn else "**Weather**")
        st.caption(
            "Open-Meteo-ийн бодит цаг агаар хотын орчныг бүрдүүлнэ; тоглоомын өдөр, шөнийг Хотын дарга удирдана. Цаг агаар санал, дүрэм, чадварт нөлөөлөхгүй. Data & Insights-д түүхэн цаг агаарын шинжилгээ бий."
            if mn else
            "Live Open-Meteo weather sets the town's atmosphere. The Mayor controls game phases; weather does not affect rules or votes. Historical analysis is on Data & Insights."
        )
        st.markdown("**Нууцлал**" if mn else "**Privacy**")
        st.markdown(
            "- Өрөө, тоглогчийн нэр, дүр, санал, үйлдэл Supabase-д хадгалагдана. Нийтийн чат амьд тоглогчдод, мафийн шөнийн чат зөвхөн мафид харагдана."
            "\n- Чат үе солигдоход цэвэрлэгдэнэ; өрөө, тоглогч, санал, үйлдлийн бүртгэл автоматаар устахгүй."
            "\n- Имэйл, нууц үг, төхөөрөмжийн байршил авахгүй. Open-Meteo-д тогтмол Улаанбаатарын координат ашиглана. Нууц мэдээлэл бүү оруулаарай."
            "\n- Data & Insights зөвхөн нээлттэй цаг агаарын өгөгдөл ашиглана."
            if mn else
            "- Room records, names, roles, votes, and actions are stored in Supabase. Living players can see public chat; Mafia chat is visible only to Mafia."
            "\n- Chat is cleared as phases change. Room, player, vote, and action records are not automatically deleted."
            "\n- The app does not request email, password, or device location. Open-Meteo uses fixed Ulaanbaatar coordinates. Do not enter sensitive information."
            "\n- Data & Insights uses public weather data only."
        )


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
        current_player = next(
            (player for player in players if player["id"] == player_id),
            None,
        )
        phase = room.get("phase", "lobby")
        if current_player and phase in {"day", "night"}:
            _heartbeat_player(db, room_id, str(player_id))
        players = _sync_presence_and_observers(db, room_id, players, phase, lang, room)
        phase = room.get("phase", phase)
        contestants = [p for p in players if not p.get("is_host")]
        current_player = next(
            (player for player in players if player["id"] == player_id),
            None,
        )

        if phase in {"day", "night"}:
            phase_label = (
                f"{'☀️ Өдөр' if phase == 'day' else '🌙 Шөнө'} · Раунд {room.get('round_number', 1)}"
                if mn else
                f"{'☀️ Day' if phase == 'day' else '🌙 Night'} · Round {room.get('round_number', 1)}"
            )
            st.caption(phase_label)
        room_col, player_col, role_col, weather_col = st.columns(
            [1.15, .85, 1.65, 2.2], vertical_alignment="top"
        )
        with room_col.container(border=True):
            st.caption("Өрөөний код" if mn else "Room code")
            st.code(room["code"])
        with player_col.container(border=True):
            st.caption("Тоглогч" if mn else "Players")
            st.markdown(f"**{len(contestants)} / {ROOM_CAPACITY}**")
        with role_col.container(border=True):
            if current_player and current_player.get("role"):
                role_names = {
                    "mafia": ("Мафийн тал", "Mafia"),
                    "doctor": ("Эмч", "Doctor"),
                    "detective": ("Цагдаа", "Detective"),
                    "citizen": ("Иргэн", "Citizen"),
                }
                role_name = role_names.get(current_player["role"], ("Тоглогч", "Player"))[0 if mn else 1]
                player_name = current_player.get("name") or ("Тоглогч" if mn else "Player")
                role_image, role_text = st.columns([.42, 1], vertical_alignment="center")
                with role_image:
                    st.image(
                        ASSET_DIR / _private_role_portrait(current_player["role"], str(player_id)),
                        width=112,
                        alt=f"{player_name} · {role_name}",
                    )
                with role_text:
                    st.caption(player_name)
                    st.markdown(f"**{role_name}**")
            elif current_player and current_player.get("is_host"):
                st.caption("Хотын дарга" if mn else "Mayor · host")
                st.caption("Нууц дүргүй · санал өгөхгүй" if mn else "No role · no vote")
            else:
                st.caption("Ажиглагч" if mn else "Spectator")
        with weather_col.container(border=True):
            can_leave = bool(
                current_player
                and phase in {"day", "night"}
                and not current_player.get("is_host")
                and current_player.get("is_alive", True)
            )
            if can_leave:
                weather_info, room_options = st.columns([8, .55], vertical_alignment="center")
                with weather_info:
                    _render_real_world_context(lang, phase)
                with room_options:
                    with st.popover("⋯", help="Тоглоомын сонголт" if mn else "Game options"):
                        if st.button("Тоглоомоос гарах" if mn else "Leave game", key=f"leave_mafia_game_{player_id}"):
                            _leave_current_game(db, room_id, player_id, current_player, players, mn)
            else:
                _render_real_world_context(lang, phase)

        round_number = int(room.get("round_number", 1))
        if phase == "night":
            with st.expander("Хотын оролцогчид" if mn else "Town residents", expanded=False):
                _render_player_seats(players, room_id, lang, phase)
        elif phase != "day":
            st.subheader("Хотын оролцогчид" if mn else "Town residents")
            _render_player_seats(players, room_id, lang, phase)
        current_player = next(
            (player for player in players if player["id"] == player_id),
            None,
        )
        is_host = bool(current_player and current_player.get("is_host"))

        if current_player and current_player.get("is_observer") and phase in {"day", "night"}:
            st.caption(
                "Та ажиглагч горимд байна. Тоглоом бусад тоглогчоор үргэлжилнэ."
                if mn else "You are spectating. The remaining players can continue the game."
            )

        if phase != "lobby":
            _render_latest_public_event(db, room_id, players)
        if is_host and phase in {"day", "finished"}:
            _render_mayor_night_report(db, room_id, players, round_number, lang)

        if phase == "lobby":
            start_col, refresh_col = st.columns([2, 1], vertical_alignment="bottom")
            with start_col:
                if is_host:
                    st.caption(
                        "Өрөөний кодыг найзууддаа явуул. 2-оос доошгүй тоглогч орсны дараа эхлүүлнэ."
                        if mn else
                        "Share the room code. The game unlocks when at least two players join."
                    )
                    if st.button(
                        "🎮 Тоглоом эхлүүлэх" if mn else "🎮 Start game",
                        key="start_mafia_game",
                        disabled=len(contestants) < 2,
                    ):
                        if len(contestants) >= 2:
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
            with refresh_col:
                if st.button("Шинэчлэх" if mn else "Refresh", key="refresh_mafia_room"):
                    st.rerun()

        elif phase == "day":
            with st.container(border=True):
                _render_day_chat_and_vote(
                    db, room_id, player_id, players,
                    round_number, is_host, lang,
                )
        elif phase == "night":
            with st.container(border=True):
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
            if is_host:
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
        if phase != "lobby" and st.button("Шинэчлэх" if mn else "Refresh", key="refresh_mafia_room"):
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


def _leave_current_game(
    db, room_id: str, player_id: str, current_player: dict,
    players: list[dict], mn: bool,
) -> None:
    try:
        db.table("game_players").update({"is_alive": False}).eq(
            "id", player_id
        ).execute()
        after_leave = [
            {**player, "is_alive": False} if player["id"] == player_id else player
            for player in players
        ]
        winner = _game_winner(after_leave)
        if winner:
            db.table("game_rooms").update({"phase": "finished"}).eq(
                "id", room_id
            ).execute()
        role_notice = (
            " Мафийн нэг гишүүн тоглолтоос гарлаа." if mn
            else " A Mafia member left the game."
        ) if current_player.get("role") == "mafia" else ""
        leave_event = (
            f"📣 {current_player['name']} тоглоомоос гарлаа. "
            f"{'Иргэд яллаа!' if winner == 'citizens' else 'Мафийн тал яллаа!' if winner == 'mafia' else 'Үлдсэн тоглогчид үргэлжлүүлнэ.'}{role_notice}"
            if mn else
            f"📣 {current_player['name']} left the game. "
            f"{'The citizens win!' if winner == 'citizens' else 'The Mafia wins!' if winner == 'mafia' else 'The remaining players continue.'}{role_notice}"
        )
        _record_public_event(db, room_id, players, leave_event)
        st.rerun()
    except Exception as exc:
        st.error("Тоглоомоос гаргаж чадсангүй." if mn else "Could not leave the game.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _clear_room_chat(db, room_id: str) -> None:
    """Keep chat scoped to the current game phase."""
    try:
        db.table("game_messages").delete().eq("room_id", room_id).neq(
            "body", "__presence__"
        ).execute()
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
            st.markdown(
                '<div style="margin:.2rem 0;padding:.55rem .75rem;'
                'border-left:4px solid #e2be67;border-radius:8px;'
                'background:rgba(20,31,48,.92);color:#f3ecd9;font-size:.95rem">'
                f'📣 {html.escape(event[2:])}</div>',
                unsafe_allow_html=True,
            )
    except Exception:
        pass


def _heartbeat_player(db, room_id: str, player_id: str) -> None:
    """Keep one private heartbeat row per player in the existing chat table."""
    key = f"mafia_presence_at_{room_id}_{player_id}"
    now = datetime.now(timezone.utc).timestamp()
    if now - float(st.session_state.get(key, 0)) < 15:
        return
    try:
        rows = (
            db.table("game_messages")
            .select("id")
            .eq("room_id", room_id)
            .eq("player_id", player_id)
            .eq("body", "__presence__")
            .limit(1)
            .execute()
            .data
        )
        if rows:
            db.table("game_messages").delete().eq("room_id", room_id).eq(
                "player_id", player_id
            ).eq("body", "__presence__").execute()
        db.table("game_messages").insert({
            "room_id": room_id,
            "player_id": player_id,
            "body": "__presence__",
        }).execute()
        st.session_state[key] = now
    except Exception:
        # Presence is best-effort; a missing marker must never block play.
        return


def _sync_presence_and_observers(
    db, room_id: str, players: list[dict], phase: str, lang: str, room: dict
) -> list[dict]:
    """Turn players inactive for two minutes into observers during a live game."""
    if phase not in {"day", "night"}:
        return players
    try:
        rows = (
            db.table("game_messages")
            .select("player_id, created_at")
            .eq("room_id", room_id)
            .eq("body", "__presence__")
            .execute()
            .data
        )
    except Exception:
        return players

    last_seen: dict[str, datetime] = {}
    for row in rows:
        try:
            seen_at = datetime.fromisoformat(
                str(row["created_at"]).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        player_id = row.get("player_id")
        if player_id and (player_id not in last_seen or seen_at > last_seen[player_id]):
            last_seen[player_id] = seen_at

    now = datetime.now(timezone.utc)
    updated_players = []
    disconnected_ids = []
    for player in players:
        updated = dict(player)
        seen_at = last_seen.get(player["id"])
        disconnected = bool(
            seen_at
            and player.get("is_alive", True)
            and (now - seen_at).total_seconds() > PRESENCE_TIMEOUT_SECONDS
        )
        updated["is_observer"] = not player.get("is_alive", True) or disconnected
        if disconnected and not player.get("is_host"):
            disconnected_ids.append(player["id"])
            updated["is_alive"] = False
        updated_players.append(updated)

    newly_disconnected_ids = []
    for disconnected_id in disconnected_ids:
        try:
            result = (
                db.table("game_players")
                .update({"is_alive": False})
                .eq("id", disconnected_id)
                .eq("is_alive", True)
                .select("id")
                .execute()
            )
            if result.data:
                newly_disconnected_ids.append(disconnected_id)
        except Exception:
            pass

    if newly_disconnected_ids:
        winner = _game_winner(updated_players)
        if winner:
            room["phase"] = "finished"
            try:
                db.table("game_rooms").update({"phase": "finished"}).eq(
                    "id", room_id
                ).execute()
            except Exception:
                pass
        for player in updated_players:
            if player["id"] in newly_disconnected_ids:
                role_notice = (
                    " Энэ тоглогч мафийн нэг гишүүн байлаа."
                    if player.get("role") == "mafia" and lang == "mn" else
                    " This player was a Mafia member."
                    if player.get("role") == "mafia" else ""
                )
                message = (
                    f"{player['name']} холболт тасарч ажиглагч боллоо. "
                    f"{'Мафийн тал яллаа.' if winner == 'mafia' else 'Иргэд яллаа.' if winner == 'citizens' else 'Тоглоом үргэлжилнэ.'}{role_notice}"
                    if lang == "mn" else
                    f"{player['name']} disconnected and is now spectating. "
                    f"{'The Mafia wins.' if winner == 'mafia' else 'The citizens win.' if winner == 'citizens' else 'The game continues.'}{role_notice}"
                )
                _record_public_event(db, room_id, players, message)
    return updated_players


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
    is_detective = bool(
        current_player
        and current_player.get("is_alive", True)
        and current_player.get("role") == "detective"
    )
    tab_labels = [
        "🗳️ Санал" if mn else "🗳️ Vote",
        "💬 Чат" if mn else "💬 Chat",
    ]
    if is_detective:
        tab_labels.append("🕵️ Цагдаа" if mn else "🕵️ Detective")
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        st.caption(
            "Хасах хүний карт дээр саналын товчийг дарна уу."
            if mn else "Choose a player's card and press Vote."
        )
        _render_player_seats(
            players,
            room_id,
            lang,
            "day",
            db=db,
            viewer=current_player,
            round_number=round_number,
        )
        _render_day_vote_status(
            db, room_id, player_id, players, round_number,
            is_host, current_player, lang,
        )

    with tabs[1]:
        _render_public_day_chat(db, room_id, player_id, players, lang)

    if is_detective:
        with tabs[2]:
            _render_detective_action(
                db, room_id, player_id, players, round_number, lang
            )


def _render_public_day_chat(
    db, room_id: str, player_id: str, players: list[dict], lang: str,
) -> None:
    mn = lang == "mn"
    current_player = next((player for player in players if player["id"] == player_id), None)
    can_chat = bool(current_player and current_player.get("is_alive", True))
    st.subheader("💬 Өдрийн чат" if mn else "💬 Public day chat")
    if not can_chat:
        st.info(
            "Та ажиглаж болно, гэхдээ чат бичихгүй."
            if mn else "You can spectate, but cannot send chat messages."
        )
    with st.form(f"mafia_chat_form_{player_id}", clear_on_submit=True):
        message = st.text_input("Мессеж" if mn else "Message", disabled=not can_chat)
        send_message = st.form_submit_button("Илгээх" if mn else "Send", disabled=not can_chat)
    if send_message and can_chat and message.strip():
        if message.lstrip().startswith(("__presence__", "__mafia__:", "📣 ")):
            st.warning(
                "Энэ мессежийн эхлэл нөөцлөгдсөн байна. Өөр текст оруулна уу."
                if mn else "That message prefix is reserved. Please use different text."
            )
        else:
            try:
                db.table("game_messages").insert({
                    "room_id": room_id,
                    "player_id": player_id,
                    "body": message.strip()[:500],
                }).execute()
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
            .order("created_at", desc=True)
            .limit(20)
            .execute()
            .data
        )
        player_names = {
            player["id"]: ("Mayor" if not mn else "Хотын дарга")
            if player.get("is_host") else player["name"]
            for player in players
        }
        visible = [
            item for item in reversed(messages)
            if not str(item.get("body", "")).startswith(("__presence__", "__mafia__:"))
        ]
        with st.container(height=210, border=True):
            if visible:
                for item in visible:
                    sender = player_names.get(item["player_id"], "Player")
                    st.write(f"**{sender}:** {item['body']}")
            else:
                st.caption("Одоогоор мессеж алга." if mn else "No messages yet.")
    except Exception as exc:
        st.error("Чат ачаалж чадсангүй." if mn else "Could not load chat.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _render_day_vote_status(
    db, room_id: str, player_id: str, players: list[dict], round_number: int,
    is_host: bool, current_player: dict | None, lang: str,
) -> None:
    mn = lang == "mn"
    st.caption("Саналын явц" if mn else "Vote progress")
    alive_players = [
        player for player in players
        if player.get("is_alive", True) and not player.get("is_host")
    ]
    targets = [player for player in alive_players if player["id"] != player_id]

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
        my_vote = next(
            (vote for vote in votes if vote.get("voter_id") == player_id),
            None,
        )
        current_target = next(
            (p for p in alive_players if my_vote and p["id"] == my_vote.get("target_id")),
            None,
        )

        tally = {}
        for vote in votes:
            target_id = vote["target_id"]
            tally[target_id] = tally.get(target_id, 0) + 1

        vote_status = (
            f"Санал: {len(votes)}/{len(alive_players)}" if mn
            else f"Votes: {len(votes)}/{len(alive_players)}"
        )
        if current_target:
            vote_status += (
                f" · Таны сонголт: {current_target['name']}" if mn
                else f" · Your vote: {current_target['name']}"
            )
        st.caption(vote_status)

        with st.expander("Саналын дэлгэрэнгүй" if mn else "Vote tally"):
            for target in alive_players:
                count = tally.get(target["id"], 0)
                st.write(f"• {target['name']}: {count}")

        if is_host:
            if len(votes) < len(alive_players):
                st.caption(
                    "Амьд тоглогч бүр санал өгсний дараа Хотын дарга шийднэ."
                    if mn else "The Mayor can resolve the vote after every living player has voted."
                )
            elif st.button(
                "Санал тооцоолж, шөнө эхлүүлэх"
                if mn else "Mayor: resolve vote and start night",
                key=f"resolve_day_{round_number}",
            ):
                _resolve_day_vote(
                    db, room_id, round_number, votes, alive_players, players, mn
                )
        elif can_vote:
            st.caption(
                "Бүх амьд тоглогч саналаа өгсний дараа Хотын дарга өдрийг дуусгана."
                if mn else "The Mayor will end the day after every living player votes."
            )

    except Exception as exc:
        st.error("Саналын дүнг авч чадсангүй." if mn else "Could not load vote totals.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")

def _render_mafia_chat(db, room_id: str, player_id: str, players: list[dict], lang: str) -> None:
    """Show night messages only in living Mafia players' sessions."""
    mn = lang == "mn"
    me = next((player for player in players if player["id"] == player_id), None)
    if not me or me.get("role") != "mafia" or not me.get("is_alive", True):
        return

    st.subheader("🤫 Нууц мафийн чат" if mn else "🤫 Private Mafia chat")
    with st.form(f"mafia_private_chat_{player_id}", clear_on_submit=True):
        text = st.text_input("Мессеж" if mn else "Message", max_chars=400)
        send = st.form_submit_button("Илгээх" if mn else "Send")
    if send and text.strip():
        try:
            db.table("game_messages").insert({
                "room_id": room_id,
                "player_id": player_id,
                "body": "__mafia__:" + text.strip()[:400],
            }).execute()
            st.rerun()
        except Exception as exc:
            st.error("Нууц мессеж илгээж чадсангүй." if mn else "Could not send private message.")
            with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                st.code(f"{type(exc).__name__}: {exc}")

    mafia_ids = {
        player["id"] for player in players
        if player.get("role") == "mafia" and player.get("is_alive", True)
    }
    try:
        rows = (
            db.table("game_messages")
            .select("player_id, body, created_at")
            .eq("room_id", room_id)
            .order("created_at")
            .limit(50)
            .execute()
            .data
        )
        names = {player["id"]: player["name"] for player in players}
        shown = [
            row for row in rows
            if row.get("player_id") in mafia_ids
            and str(row.get("body", "")).startswith("__mafia__:")
        ]
        if not shown:
            st.caption("Одоогоор мессеж алга." if mn else "No messages yet.")
        for row in shown:
            st.write(f"**{names.get(row['player_id'], 'Mafia')}:** {row['body'][10:]}")
    except Exception as exc:
        st.error("Нууц чатыг ачаалж чадсангүй." if mn else "Could not load private chat.")
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _game_winner(players: list[dict]) -> str | None:
    alive = [p for p in players if p.get("is_alive", True) and not p.get("is_host")]
    mafia = sum(1 for p in alive if p.get("role") == "mafia")
    ordinary_citizens = sum(1 for p in alive if p.get("role") == "citizen")
    if mafia == 0:
        return "citizens"
    if ordinary_citizens == 0:
        return "mafia"
    return None


def _resolve_day_vote(
    db, room_id: str, round_number: int, votes: list[dict],
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
        "phase": "finished" if winner else "night",
        "round_number": round_number if winner else round_number + 1,
    }).eq("id", room_id).execute()

    player_names = {p["id"]: p["name"] for p in alive_players}
    tally_text = ", ".join(
        f"{player_names.get(p['id'], 'Player')}: {tally.get(p['id'], 0)}"
        for p in alive_players
    )
    if eliminated:
        eliminated_name = player_names.get(eliminated, "Player")
        eliminated_player = next(
            (player for player in alive_players if player["id"] == eliminated),
            None,
        )
        mafia_revealed = bool(
            eliminated_player and eliminated_player.get("role") == "mafia"
        )
        role_notice = (
            " Тэр мафийн нэг гишүүн байлаа." if mn
            else " They were a Mafia member."
        ) if mafia_revealed else ""
        event = (
            f"📊 Өдрийн саналын дүн — {tally_text}. {eliminated_name} олонхийн саналаар хасагдлаа.{role_notice} Шөнө эхэллээ."
            if mn else
            f"📊 Day vote results — {tally_text}. {eliminated_name} was eliminated by the vote.{role_notice} Night begins."
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


def _cast_day_vote(
    db, room_id: str, round_number: int, voter_id: str, target_id: str
) -> None:
    existing = (
        db.table("game_votes").select("id")
        .eq("room_id", room_id).eq("round_number", round_number)
        .eq("phase", "day").eq("voter_id", voter_id)
        .limit(1).execute().data
    )
    vote = {
        "room_id": room_id,
        "round_number": round_number,
        "phase": "day",
        "voter_id": voter_id,
        "target_id": target_id,
    }
    if existing:
        db.table("game_votes").update({"target_id": target_id}).eq(
            "id", existing[0]["id"]
        ).execute()
    else:
        db.table("game_votes").insert(vote).execute()


def _get_saved_night_target(db, room_id: str, round_number: int, player_id: str) -> str | None:
    try:
        rows = (
            db.table("game_votes")
            .select("target_id")
            .eq("room_id", room_id)
            .eq("round_number", round_number)
            .eq("phase", "night")
            .eq("voter_id", player_id)
            .limit(1)
            .execute()
            .data
        )
        return str(rows[0]["target_id"]) if rows else None
    except Exception:
        return None


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

    if me and me.get("is_alive", True) and me.get("role") == "mafia":
        _render_mafia_chat(db, room_id, player_id, players, lang)

    if me and me.get("is_alive", True) and me.get("role") == "mafia" and targets:
        st.subheader("🌙 Мафийн сонголт" if mn else "🌙 Mafia action")
        choices = {p["name"]: p["id"] for p in targets}
        saved_target = _get_saved_night_target(db, room_id, round_number, player_id)
        saved_target_name = next(
            (name for name, target_id in choices.items() if target_id == saved_target),
            None,
        )
        target_names = list(choices)
        target_index = target_names.index(saved_target_name) if saved_target_name in target_names else 0
        with st.form(f"mafia_night_{round_number}"):
            selected = st.selectbox(
                "Хэнийг онилох вэ?" if mn else "Choose a target",
                target_names,
                index=target_index,
                key=f"mafia_target_{round_number}_{player_id}",
            )
            send = st.form_submit_button(
                "✅ Сонголт хадгалсан · өөрчлөх" if mn and saved_target else
                "🎯 Зорилго сонгох" if mn else
                "✅ Saved · change target" if saved_target else
                "🎯 Choose target",
                type="primary" if saved_target else "secondary",
            )
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
        heal_choices = {p["name"]: p["id"] for p in alive}
        saved_target = _get_saved_night_target(db, room_id, round_number, player_id)
        saved_target_name = next(
            (name for name, target_id in heal_choices.items() if target_id == saved_target),
            None,
        )
        heal_names = list(heal_choices)
        heal_index = heal_names.index(saved_target_name) if saved_target_name in heal_names else 0
        with st.form(f"doctor_night_{round_number}"):
            selected_heal = st.selectbox(
                "Хэнийг эмчлэх вэ?" if mn else "Who do you protect?",
                heal_names,
                index=heal_index,
                key=f"doctor_target_{round_number}_{player_id}",
            )
            heal = st.form_submit_button(
                "✅ Хадгалсан · өөрчлөх" if mn and saved_target else
                "🛡️ Хамгаалах" if mn else
                "✅ Saved · change protection" if saved_target else
                "🛡️ Protect",
                type="primary" if saved_target else "secondary",
            )
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
        ready = len(mafia_votes) >= len(mafia) and len(doctor_votes) >= len(doctors)
        if not ready:
            st.caption("Мафийнхан болон амьд эмч сонголтоо хийсний дараа шөнийг дуусгана." if mn else "Wait for the living Mafia and Doctor to submit their actions.")
        elif me and me.get("is_observer"):
            st.caption("Ажиглагчид Хотын даргын шилжилтийг хүлээнэ." if mn else "Observers are waiting for the Mayor to advance the phase.")
        elif me and me.get("is_host") and st.button(
            "Хотын дарга: шөнийг дуусгах" if mn else "Mayor: resolve night",
            key=f"resolve_night_{round_number}",
        ):
            _resolve_night(db, room_id, round_number, mafia_votes, doctor_votes, players, mn)
        elif me and not me.get("is_host"):
            st.caption("Шөнийн үйлдлүүд дууслаа. Хотын дарга өглөөг эхлүүлнэ." if mn else "Night actions are ready. The Mayor will start the day.")
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
    db.table("game_rooms").update(updates).eq("id", room_id).execute()

    victim_name = next((p["name"] for p in players if p["id"] == eliminated), "Тоглогч" if mn else "A player")
    doctor_alive = any(
        player.get("role") == "doctor"
        and player.get("is_alive", True)
        and not player.get("is_host")
        for player in players
    )
    if eliminated:
        doctor_result = (
            " Эмч мафийн онилсон хүнийг хамгаалж чадсангүй."
            if mn and doctor_alive else
            " The Doctor's protection did not stop the attack."
            if doctor_alive else ""
        )
        public_text = (
            f"🌅 Өглөө боллоо. {victim_name} шөнө хасагдлаа.{doctor_result}"
            if mn else f"🌅 Morning. {victim_name} was eliminated overnight.{doctor_result}"
        )
    else:
        public_text = (
            "🌅 Өглөө боллоо. Эмч мафийн онилсон хүнийг аварлаа."
            if mn and mafia_target and mafia_target == protected else
            "🌅 Өглөө боллоо. Мафийн санал тэнцэж, хэн ч хасагдсангүй."
            if mn else
            "🌅 Morning. The Doctor saved the Mafia's target."
            if mafia_target and mafia_target == protected else
            "🌅 Morning. The Mafia vote was tied; nobody was eliminated."
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
            else:
                st.caption("Мафийн сонголт бүртгэгдээгүй." if mn else "No Mafia target was recorded.")
            for target_id in sorted(doctor_targets):
                st.write(("Эмчийн хамгаалсан хүн: " if mn else "Doctor protected: ") + names.get(target_id, "—"))
            if mafia_target and mafia_target in doctor_targets:
                st.success("Эмч мафийн онилсон хүнийг аварсан." if mn else "The Doctor saved the Mafia's target.")
            elif mafia_target:
                if doctor_targets:
                    st.info("Эмч өөр хүнийг хамгаалсан тул мафийн онилсон хүн хасагдсан." if mn else "The Doctor protected the wrong person; the Mafia's target was eliminated.")
                elif doctor_ids:
                    st.info("Эмч сонголтоо илгээгээгүй." if mn else "The Doctor did not submit a protection choice.")
                else:
                    st.caption("Энэ тоглолтод эмчийн дүр байгаагүй." if mn else "There was no Doctor in this game.")
            elif mafia_tally and doctor_targets:
                st.caption("Мафийн санал тэнцсэн тул эмчийн хамгаалалтыг зөв/буруу гэж дүгнэх онилсон хүн алга." if mn else "The Mafia vote was tied, so there was no single target to judge the Doctor's choice against.")
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
    create_col, join_col = st.columns(2)
    with create_col.container(border=True):
        st.markdown("**Өрөө нээх**" if mn else "**Host a game**")
        if st.button("Өрөө үүсгэх" if mn else "Create room", key="open_create_room", width="stretch"):
            st.session_state["mafia_entry_mode"] = "create"
    with join_col.container(border=True):
        st.markdown("**Өрөөний кодтой юу?**" if mn else "**Have a room code?**")
        if st.button("Өрөөнд нэгдэх" if mn else "Join room", key="open_join_room", width="stretch"):
            st.session_state["mafia_entry_mode"] = "join"

    mode = st.session_state.get("mafia_entry_mode")
    if not mode:
        return

    with st.container(border=True):
        if mode == "create":
            st.markdown("### "+("Шинэ өрөө" if mn else "New room"))
            with st.form("create_mafia_room"):
                host_name = st.text_input("Таны нэр" if mn else "Your name", key="create_host_name")
                create_clicked = st.form_submit_button("Өрөө үүсгэх" if mn else "Create room")
            if create_clicked:
                if not host_name.strip():
                    st.warning("Нэрээ оруулна уу." if mn else "Enter your name.")
                else:
                    try:
                        room, player = _create_mafia_room(db, host_name.strip())
                        st.session_state["mafia_room_id"] = room["id"]
                        st.session_state["mafia_player_id"] = player["id"]
                        st.session_state.pop("mafia_entry_mode", None)
                        st.rerun()
                    except Exception as exc:
                        st.error("Өрөө үүсгэж чадсангүй." if mn else "Could not create room.")
                        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                            st.code(f"{type(exc).__name__}: {exc}")
        else:
            st.markdown("### "+("Өрөөнд нэгдэх" if mn else "Join a room"))
            with st.form("join_mafia_room"):
                player_name = st.text_input("Таны нэр" if mn else "Your name", key="join_player_name")
                room_code = st.text_input("Өрөөний код" if mn else "Room code", key="join_room_code")
                join_clicked = st.form_submit_button("Нэгдэх" if mn else "Join room")
            if join_clicked:
                player_name = player_name.strip()
                room_code = room_code.strip().upper()
                if not player_name or not room_code:
                    st.warning("Нэр болон өрөөний кодоо оруулна уу." if mn else "Enter your name and room code.")
                else:
                    try:
                        rooms = (
                            db.table("game_rooms").select("id, code, phase")
                            .eq("code", room_code).limit(1).execute().data
                        )
                        if not rooms:
                            st.error("Ийм кодтой өрөө олдсонгүй." if mn else "Room code not found.")
                        elif rooms[0]["phase"] != "lobby":
                            st.error("Энэ өрөө тоглоомоо эхлүүлсэн байна." if mn else "Game already started.")
                        else:
                            room = rooms[0]
                            players = (
                                db.table("game_players").select("id, is_host")
                                .eq("room_id", room["id"]).execute().data
                            )
                            participant_count = sum(1 for p in players if not p.get("is_host"))
                            if participant_count >= ROOM_CAPACITY:
                                st.error("Өрөө дүүрсэн байна (12 тоглогч)." if mn else "Room is full (12 players).")
                            else:
                                player = (
                                    db.table("game_players").insert({
                                        "room_id": room["id"], "name": player_name,
                                        "role": None, "is_alive": True, "is_host": False,
                                    }).execute().data[0]
                                )
                                st.session_state["mafia_room_id"] = room["id"]
                                st.session_state["mafia_player_id"] = player["id"]
                                st.session_state.pop("mafia_entry_mode", None)
                                st.rerun()
                    except Exception as exc:
                        st.error("Өрөөнд нэгдэж чадсангүй." if mn else "Could not join room.")
                        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                            st.code(f"{type(exc).__name__}: {exc}")

        if st.button("Буцах" if mn else "Back", key="close_room_entry"):
            st.session_state.pop("mafia_entry_mode", None)
            st.rerun()
