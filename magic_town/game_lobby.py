import secrets
import string
import random
from datetime import datetime

import streamlit as st

from .supabase_client import get_supabase_client
from .plants import fetch_plants
from .weather import fetch_weather, weather_label

ROOM_CAPACITY = 12


@st.cache_data(ttl=900, show_spinner=False)
def _game_weather() -> dict:
    return fetch_weather()["payload"]


@st.cache_data(ttl=1800, show_spinner=False)
def _game_plants() -> dict:
    return fetch_plants()["payload"]


def _render_real_world_context(lang: str) -> None:
    mn = lang == "mn"
    try:
        payload = _game_weather()
        current = payload["current"]
        today = payload["daily"][0]
        current_time = datetime.fromisoformat(current["time"])
        sunrise = datetime.fromisoformat(today["sunrise"])
        sunset = datetime.fromisoformat(today["sunset"])
        is_daylight = sunrise <= current_time < sunset
        sky = ("Гадаа өдөр" if is_daylight else "Гадаа шөнө") if mn else ("Outside: daytime" if is_daylight else "Outside: nighttime")
        phase_text = ("Тоглоомын үе" if mn else "Game phase")
        weather_text = weather_label(int(current["weather_code"]), lang)
        st.caption(
            f"{sky} · {phase_text}: бодит нар мандах {today['sunrise'][-5:]} / жаргах {today['sunset'][-5:]} · {weather_text}"
            if mn
            else f"{sky} · Real sunrise {today['sunrise'][-5:]} / sunset {today['sunset'][-5:]} · {weather_text}"
        )
    except Exception:
        st.caption(
            "Гадаах өдөр/шөнийн бодит мэдээлэл одоогоор ачаалсангүй. Тоглоомын үе хэвийн үргэлжилнэ."
            if mn
            else "Real-world day/night data is unavailable right now. The game phase continues normally."
        )


@st.fragment(run_every="3s")
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
        contestants = [p for p in players if not p.get("is_host")]

        st.write("Өрөөний код" if mn else "Room code")
        st.code(room["code"])
        _render_real_world_context(lang)
        st.write(
            f"{'Тоглогчид' if mn else 'Players'}: "
            f"{len(contestants)} / {ROOM_CAPACITY}"
        )

        for player in players:
            host_label = " (Хотын дарга)" if mn else " (Mayor / host)"
            eliminated_label = (
                (" (хасагдсан)" if mn else " (eliminated)")
                if not player.get("is_alive", True) and not player.get("is_host")
                else ""
            )
            st.write(
                f"• {player['name']}"
                f"{host_label if player.get('is_host') else eliminated_label}"
            )

            # Тоглогч зөвхөн өөрийнхөө дүрийг харна.
            if player["id"] == player_id and player.get("role"):
                role_names = {
                    "mafia": ("Мафийн тал", "Mafia"),
                    "doctor": ("Эмч", "Doctor"),
                    "detective": ("Цагдаа", "Detective"),
                    "citizen": ("Иргэн", "Citizen"),
                }
                role_name = role_names.get(player["role"], ("Тоглогч", "Player"))[0 if mn else 1]
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
        st.subheader("🌿 Эмчийн сонголт" if mn else "🌿 Doctor action")
        try:
            records = _game_plants().get("records", [])
            named = [r for r in records if r.get("scientific_name")]
            if named:
                record = named[(round_number - 1) % len(named)]
                plant_name = record["scientific_name"]
                st.caption(
                    f"GBIF бүртгэлийн ургамал: {plant_name}. Зөвхөн тоглоомын зохиомол эмчилгээ; бодит эмчилгээний мэдээлэл биш."
                    if mn else f"GBIF record used as a fictional game remedy: {plant_name}. This is not medical advice or evidence of a real treatment."
                )
                if record.get("occurrence_url"):
                    st.markdown(f"[GBIF бүртгэлийг харах]({record['occurrence_url']})" if mn else f"[View GBIF record]({record['occurrence_url']})")
            else:
                st.info("GBIF ургамлын дата одоогоор олдсонгүй; зохиомол ургамал ашиглахгүй." if mn else "No GBIF plant record is available; no plant is invented.")
        except Exception:
            st.info("GBIF дата ачаалсангүй; эмчийн үйлдэл үргэлжилж болно." if mn else "GBIF data is unavailable; the doctor action can still continue.")

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
