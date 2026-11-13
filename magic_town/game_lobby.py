import secrets
import string
import random

import streamlit as st

from .supabase_client import get_supabase_client

ROOM_CAPACITY = 12


def render_game_lobby(lang: str) -> None:
    mn = lang == "mn"
    st.subheader("🎭 Mafia тоглоом" if mn else "🎭 Mafia game")

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

            st.write("Өрөөний код" if mn else "Room code")
            st.code(room["code"])
            st.write(
                f"{'Тоглогчид' if mn else 'Players'}: "
                f"{len(players)} / {ROOM_CAPACITY}"
            )

            for player in players:
                label = " (host)" if player.get("is_host") else ""
                st.write(f"• {player['name']}{label}")

                # Зөвхөн өөрийн дүрийг тухайн тоглогчид харуулна.
                if player["id"] == player_id and player.get("role"):
                    role_name = (
                        "Мафийн тал" if player["role"] == "mafia" else "Иргэн"
                    )
                    if not mn:
                        role_name = (
                            "Mafia" if player["role"] == "mafia" else "Citizen"
                        )
                    st.success(
                        f"Таны нууц дүр: {role_name}"
                        if mn
                        else f"Your secret role: {role_name}"
                    )

            phase = room.get("phase", "lobby")

            if phase == "lobby":
                current_player = next(
                    (p for p in players if p["id"] == player_id), None
                )
                is_host = bool(current_player and current_player.get("is_host"))

                if is_host:
                    if st.button(
                        "🎮 Тоглоом эхлүүлэх" if mn else "🎮 Start game",
                        key="start_mafia_game",
                    ):
                        if len(players) < 2:
                            st.warning(
                                "Эхлэхэд дор хаяж 2 тоглогч хэрэгтэй."
                                if mn
                                else "At least 2 players are needed to start."
                            )
                        else:
                            shuffled = [p["id"] for p in players]
                            random.shuffle(shuffled)
                            mafia_count = max(1, len(players) // 4)
                            mafia_ids = set(shuffled[:mafia_count])

                            for player in players:
                                role = (
                                    "mafia"
                                    if player["id"] in mafia_ids
                                    else "citizen"
                                )
                                (
                                    db.table("game_players")
                                    .update({"role": role})
                                    .eq("id", player["id"])
                                    .execute()
                                )

                            (
                                db.table("game_rooms")
                                .update({"phase": "day", "round_number": 1})
                                .eq("id", room_id)
                                .execute()
                            )
                            st.rerun()
                else:
                    st.info(
                        "Өрөөний эзэн тоглоом эхлүүлэхийг хүлээж байна."
                        if mn
                        else "Waiting for the host to start the game."
                    )
            else:
                st.info(
                    f"Тоглоом эхэллээ · Раунд {room.get('round_number', 1)}"
                    if mn
                    else f"Game started · Round {room.get('round_number', 1)}"
                )

            if st.button("Шинэчлэх" if mn else "Refresh"):
                st.rerun()

        except Exception as exc:
            st.error("Өрөөний мэдээлэл авч чадсангүй." if mn else "Could not load the room.")
            with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                st.code(f"{type(exc).__name__}: {exc}")
        return

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
            code = "".join(
                secrets.choice(string.ascii_uppercase + string.digits)
                for _ in range(6)
            )
            try:
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

                player = (
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
                .select("id")
                .eq("room_id", room["id"])
                .execute()
                .data
            )

            if len(players) >= ROOM_CAPACITY:
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