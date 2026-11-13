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
        _render_current_room(db, room_id, player_id, lang)
        return

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

        st.write("Өрөөний код" if mn else "Room code")
        st.code(room["code"])
        st.write(
            f"{'Тоглогчид' if mn else 'Players'}: "
            f"{len(players)} / {ROOM_CAPACITY}"
        )

        for player in players:
            host_label = " (host)" if player.get("is_host") else ""
            st.write(f"• {player['name']}{host_label}")

            # Тоглогч зөвхөн өөрийнхөө дүрийг харна.
            if player["id"] == player_id and player.get("role"):
                role_name = (
                    ("Мафийн тал" if mn else "Mafia")
                    if player["role"] == "mafia"
                    else ("Иргэн" if mn else "Citizen")
                )
                st.success(
                    f"Таны нууц дүр: {role_name}"
                    if mn
                    else f"Your secret role: {role_name}"
                )

        phase = room.get("phase", "lobby")
        current_player = next(
            (player for player in players if player["id"] == player_id),
            None,
        )
        is_host = bool(current_player and current_player.get("is_host"))

        if phase == "lobby":
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
                        player_ids = [player["id"] for player in players]
                        random.shuffle(player_ids)
                        mafia_count = max(1, len(players) // 4)
                        mafia_ids = set(player_ids[:mafia_count])

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

    st.subheader("💬 Өдрийн чат" if mn else "💬 Day chat")

    with st.form("mafia_chat_form", clear_on_submit=True):
        message = st.text_input("Мессеж" if mn else "Message")
        send_message = st.form_submit_button(
            "Илгээх" if mn else "Send"
        )

    if send_message and current_player and message.strip():
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
        player_names = {player["id"]: player["name"] for player in players}

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
        player for player in players if player.get("is_alive", True)
    ]
    targets = [
        player for player in alive_players if player["id"] != player_id
    ]

    if not current_player or not current_player.get("is_alive", True):
        st.info(
            "Та санал өгөх боломжгүй."
            if mn
            else "You cannot vote."
        )
        return

    if not targets:
        st.info(
            "Санал өгөх өөр тоглогч алга."
            if mn
            else "There are no other players to vote for."
        )
        return

    target_names = {player["name"]: player["id"] for player in targets}

    with st.form("mafia_vote_form"):
        selected_name = st.selectbox(
            "Хэнийг саналд нэр дэвшүүлэх вэ?"
            if mn
            else "Who do you vote for?",
            list(target_names.keys()),
        )
        submit_vote = st.form_submit_button(
            "Санал өгөх" if mn else "Submit vote"
        )

    if submit_vote:
        try:
            existing = (
                db.table("game_votes")
                .select("id")
                .eq("room_id", room_id)
                .eq("round_number", round_number)
                .eq("phase", "day")
                .eq("voter_id", player_id)
                .limit(1)
                .execute()
                .data
            )

            vote_data = {
                "room_id": room_id,
                "round_number": round_number,
                "phase": "day",
                "voter_id": player_id,
                "target_id": target_names[selected_name],
            }

            if existing:
                (
                    db.table("game_votes")
                    .update({"target_id": target_names[selected_name]})
                    .eq("id", existing[0]["id"])
                    .execute()
                )
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
    alive = [p for p in players if p.get("is_alive", True)]
    mafia = sum(1 for p in alive if p.get("role") == "mafia")
    citizens = sum(1 for p in alive if p.get("role") == "citizen")
    if mafia == 0:
        return "citizens"
    if mafia >= citizens:
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


def _render_night(
    db, room_id: str, player_id: str, players: list[dict],
    round_number: int, is_host: bool, lang: str,
) -> None:
    mn = lang == "mn"
    alive = [p for p in players if p.get("is_alive", True)]
    mafia = [p for p in alive if p.get("role") == "mafia"]
    targets = [p for p in alive if p.get("role") == "citizen"]
    me = next((p for p in players if p["id"] == player_id), None)

    if me and me.get("is_alive", True) and me.get("role") == "mafia":
        st.subheader("🌙 Мафийн шөнийн санал" if mn else "🌙 Mafia night action")
        if targets:
            choices = {p["name"]: p["id"] for p in targets}
            with st.form(f"night_vote_{round_number}"):
                selected = st.selectbox(
                    "Хэнийг онилох вэ?" if mn else "Choose a target",
                    list(choices),
                )
                send = st.form_submit_button(
                    "Санал өгөх" if mn else "Submit night action"
                )
            if send:
                try:
                    existing = (
                        db.table("game_votes").select("id")
                        .eq("room_id", room_id)
                        .eq("round_number", round_number)
                        .eq("phase", "night")
                        .eq("voter_id", player_id)
                        .limit(1).execute().data
                    )
                    if existing:
                        db.table("game_votes").update({
                            "target_id": choices[selected]
                        }).eq("id", existing[0]["id"]).execute()
                    else:
                        db.table("game_votes").insert({
                            "room_id": room_id,
                            "round_number": round_number,
                            "phase": "night",
                            "voter_id": player_id,
                            "target_id": choices[selected],
                        }).execute()
                    st.success(
                        "Шөнийн санал хадгалагдлаа."
                        if mn else "Night action saved."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(
                        "Шөнийн санал хадгалж чадсангүй."
                        if mn else "Could not save night action."
                    )
                    with st.expander("Техник мэдээлэл" if mn else "Technical details"):
                        st.code(f"{type(exc).__name__}: {exc}")
        else:
            st.info("Онох иргэн үлдээгүй." if mn else "No citizens remain.")
    elif me and me.get("is_alive", True):
        st.info(
            "Шөнө болж байна. Мафийн үйлдлийг хүлээнэ үү."
            if mn else "It is night. Wait for the Mafia action."
        )
    else:
        st.info(
            "Та хасагдсан. Шөнийн үр дүнг хүлээнэ үү."
            if mn else "You are eliminated. Wait for the night result."
        )

    try:
        votes = (
            db.table("game_votes")
            .select("voter_id, target_id")
            .eq("room_id", room_id)
            .eq("round_number", round_number)
            .eq("phase", "night")
            .execute().data
        )
        mafia_ids = {p["id"] for p in mafia}
        target_ids = {p["id"] for p in targets}
        valid = [
            v for v in votes
            if v.get("voter_id") in mafia_ids and v.get("target_id") in target_ids
        ]

        if is_host:
            if len(valid) < len(mafia):
                st.caption(
                    "Мафийн амьд тоглогчид саналаа өгсний дараа шөнийг дуусгана."
                    if mn else "Wait for all living Mafia players to vote."
                )
            elif st.button(
                "Шөнийг дуусгах" if mn else "Resolve night",
                key=f"resolve_night_{round_number}",
            ):
                _resolve_night(db, room_id, round_number, valid, players, mn)
        else:
            st.caption(
                "Өрөөний эзэн шөнийн үр дүнг баталгаажуулна."
                if mn else "The host will resolve the night."
            )
    except Exception as exc:
        st.error(
            "Шөнийн саналыг уншиж чадсангүй."
            if mn else "Could not load night actions."
        )
        with st.expander("Техник мэдээлэл" if mn else "Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")


def _resolve_night(
    db, room_id: str, round_number: int, votes: list[dict],
    players: list[dict], mn: bool,
) -> None:
    tally: dict[str, int] = {}
    for vote in votes:
        target = vote["target_id"]
        tally[target] = tally.get(target, 0) + 1
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
    winner = _game_winner(after)
    updates = {"phase": "finished" if winner else "day"}
    if not winner:
        updates["round_number"] = round_number + 1
    db.table("game_rooms").update(updates).eq("id", room_id).execute()

    if eliminated:
        name = next((p["name"] for p in players if p["id"] == eliminated), "Player")
        if mn:
            outcome = (
                "Мафийн тал яллаа!" if winner == "mafia"
                else "Иргэд яллаа!" if winner == "citizens"
                else "Өдөр эхэллээ."
            )
            st.info(f"Шөнө {name} хасагдлаа. {outcome}")
        else:
            outcome = (
                "The Mafia wins!" if winner == "mafia"
                else "The citizens win!" if winner == "citizens"
                else "Day begins."
            )
            st.info(f"{name} was eliminated at night. {outcome}")
    else:
        st.info(
            "Шөнийн санал тэнцлээ. Хэн ч хасагдсангүй. Өдөр эхэллээ."
            if mn else "Night vote tied. Nobody was eliminated. Day begins."
        )
    st.rerun()

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