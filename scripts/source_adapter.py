import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


API_BASE = "https://api.cloudflare.ravensburgerplay.com/hydraproxy/api/v2"
EVENT_ID = os.getenv("EVENT_ID", "1007231")

BASE = Path(__file__).resolve().parents[1]
DATA_FILE = BASE / "data" / "event.json"

HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://tcg.ravensburgerplay.com/",
    "User-Agent": "Mozilla/5.0 LorcanaPlayerDashboard/1.0",
}


def api_get(path, params=None):
    url = f"{API_BASE}{path}"

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def load_tracked_players():
    """
    Keep the manually selected/tracked players from data/event.json.

    This means your Discord tags such as Q2W, OSA, IDK, etc.
    are preserved even though Ravensburger does not provide them.
    """

    if not DATA_FILE.exists():
        return {}

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    result = {}

    for player in data.get("players", []):
        name = player.get("name")

        if name:
            result[name.lower()] = {
                "name": name,
                "tag": player.get("tag", ""),
            }

    return result


def get_name(value):
    """
    Extract a player/display name from the many possible shapes
    used by the Ravensburger API.
    """

    if value is None:
        return None

    if isinstance(value, str):
        return value.strip() or None

    if isinstance(value, dict):
        for key in (
            "display_name",
            "username",
            "user_name",
            "screen_name",
            "name",
            "nickname",
            "handle",
        ):
            candidate = value.get(key)

            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

        user = value.get("user")

        if isinstance(user, dict):
            return get_name(user)

    return None


def get_player_name(obj):
    if not isinstance(obj, dict):
        return get_name(obj)

    for key in (
        "player",
        "participant",
        "user",
        "registration",
        "player_profile",
        "profile",
    ):
        if key in obj:
            name = get_name(obj[key])

            if name:
                return name

    return get_name(obj)


def get_items(payload):
    """
    Normalize paginated/list API responses.
    """

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in (
        "results",
        "items",
        "registrations",
        "standings",
        "matches",
    ):
        value = payload.get(key)

        if isinstance(value, list):
            return value

    return []


def get_all_registrations(event_id):
    registrations = []

    page = 1

    while page <= 20:
        payload = api_get(
            f"/events/{event_id}/registrations/",
            {
                "page": page,
                "page_size": 100,
            },
        )

        items = get_items(payload)

        if not items:
            break

        registrations.extend(items)

        next_page = (
            payload.get("next_page_number")
            if isinstance(payload, dict)
            else None
        )

        if next_page:
            page = next_page
        elif len(items) < 100:
            break
        else:
            page += 1

    return registrations


def get_rounds(event):
    rounds = []

    for phase in event.get("tournament_phases", []) or []:
        for rnd in phase.get("rounds", []) or []:
            if rnd.get("id") is not None:
                rounds.append(rnd)

    return rounds


def round_number(rnd):
    try:
        return int(rnd.get("round_number") or 0)
    except Exception:
        return 0


def get_all_standings(round_id):
    standings = []

    page = 1

    while page <= 20:
        payload = api_get(
            f"/tournament-rounds/{round_id}/standings/paginated/",
            {
                "page": page,
                "page_size": 100,
            },
        )

        items = get_items(payload)

        if not items:
            # Older tournaments sometimes expose the non-paginated endpoint.
            try:
                fallback = api_get(
                    f"/tournament-rounds/{round_id}/standings/"
                )

                fallback_items = get_items(fallback)

                if fallback_items:
                    return fallback_items
            except Exception:
                pass

            break

        standings.extend(items)

        next_page = (
            payload.get("next_page_number")
            if isinstance(payload, dict)
            else None
        )

        if next_page:
            page = next_page
        elif len(items) < 100:
            break
        else:
            page += 1

    return standings


def get_all_matches(round_id):
    matches = []

    page = 1

    while page <= 20:
        payload = api_get(
            f"/tournament-rounds/{round_id}/matches/paginated/",
            {
                "page": page,
                "page_size": 100,
            },
        )

        items = get_items(payload)

        if not items:
            break

        matches.extend(items)

        next_page = (
            payload.get("next_page_number")
            if isinstance(payload, dict)
            else None
        )

        if next_page:
            page = next_page
        elif len(items) < 100:
            break
        else:
            page += 1

    return matches


def find_player_name_in_match(match, target_name):
    """
    Determine whether target_name participates in a match and return
    the opponent name.
    """

    if not isinstance(match, dict):
        return None

    target = target_name.lower()

    # Common two-player structures.
    candidates = []

    for key in (
        "player1",
        "player2",
        "player_a",
        "player_b",
        "player_one",
        "player_two",
        "home_player",
        "away_player",
        "participant1",
        "participant2",
        "player",
        "opponent",
    ):
        if key in match:
            name = get_name(match[key])

            if name:
                candidates.append(name)

    # Nested players list.
    for key in ("players", "participants"):
        value = match.get(key)

        if isinstance(value, list):
            for item in value:
                name = get_name(item)

                if name:
                    candidates.append(name)

    candidates = list(dict.fromkeys(candidates))

    if not candidates:
        return None

    target_found = any(name.lower() == target for name in candidates)

    if not target_found:
        # Sometimes the API gives first/last name fields instead of username.
        text = json.dumps(match, ensure_ascii=False).lower()

        if target not in text:
            return None

    for name in candidates:
        if name.lower() != target:
            return name

    return "—"


def extract_record(value):
    """
    Convert values such as:
        3-1-0
        3–1
        {'wins': 3, 'losses': 1}
    into wins/losses.
    """

    if isinstance(value, dict):
        wins = value.get("wins")
        losses = value.get("losses")

        if wins is not None or losses is not None:
            return (
                int(wins or 0),
                int(losses or 0),
            )

        for key in ("record", "match_record", "matchRecord"):
            if key in value:
                return extract_record(value[key])

    if isinstance(value, str):
        cleaned = value.replace("–", "-").replace("—", "-")

        parts = cleaned.split("-")

        if len(parts) >= 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                pass

    return None, None


def find_standing(standings, player_name):
    target = player_name.lower()

    for standing in standings:
        name = get_player_name(standing)

        if name and name.lower() == target:
            return standing

        # Also search the serialized object as a fallback.
        try:
            serialized = json.dumps(
                standing,
                ensure_ascii=False,
            ).lower()

            if target in serialized:
                return standing
        except Exception:
            pass

    return None


def value_from(obj, *keys):
    if not isinstance(obj, dict):
        return None

    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]

    return None


def normalize_player(
    tracked,
    standing=None,
    matches=None,
    current_round=None,
):
    name = tracked["name"]

    standing = standing or {}
    matches = matches or []

    rank = value_from(
        standing,
        "rank",
        "placement",
        "position",
    )

    points = value_from(
        standing,
        "points",
        "match_points",
        "total_points",
    )

    wins = value_from(
        standing,
        "match_wins",
        "wins",
        "matchWins",
    )

    losses = value_from(
        standing,
        "match_losses",
        "losses",
        "matchLosses",
    )

    games_won = value_from(
        standing,
        "game_wins",
        "games_won",
        "gameWins",
    )

    games_lost = value_from(
        standing,
        "game_losses",
        "games_lost",
        "gameLosses",
    )

    # Try record objects/strings if explicit fields weren't present.
    if wins is None or losses is None:
        record = value_from(
            standing,
            "record",
            "match_record",
            "matchRecord",
        )

        rw, rl = extract_record(record)

        if wins is None:
            wins = rw

        if losses is None:
            losses = rl

    opponent = "—"

    normalized_matches = []

    for match in matches:
        opp = find_player_name_in_match(match, name)

        if not opp:
            continue

        opponent = opp

        result = "?"

        # Try to identify the result.
        serialized = json.dumps(
            match,
            ensure_ascii=False,
        ).lower()

        if "win" in serialized:
            result = "W"
        elif "loss" in serialized:
            result = "L"

        normalized_matches.append(
            {
                "round": current_round,
                "opponent": opp,
                "result": result,
                "score": value_from(
                    match,
                    "score",
                    "result",
                    "game_score",
                ) or "—",
                "table": value_from(
                    match,
                    "table",
                    "table_number",
                ),
            }
        )

    return {
        "name": name,
        "tag": tracked.get("tag", ""),
        "rank": rank,
        "points": points,
        "match_wins": wins,
        "match_losses": losses,
        "game_wins": games_won,
        "game_losses": games_lost,
        "opponent": opponent,
        "status": value_from(
            standing,
            "status",
        ) or "active",
        "matches": normalized_matches,
    }


def get_fresh_data():
    event = api_get(f"/events/{EVENT_ID}/")

    tracked = load_tracked_players()

    registrations = get_all_registrations(EVENT_ID)

    registered_names = []

    for registration in registrations:
        name = get_player_name(registration)

        if name:
            registered_names.append(name)

    rounds = get_rounds(event)

    # Prefer the latest round that has standings.
    rounds_sorted = sorted(
        rounds,
        key=round_number,
        reverse=True,
    )

    selected_round = None
    selected_standings = []
    selected_matches = []

    for rnd in rounds_sorted:
        try:
            standings = get_all_standings(rnd["id"])

            if standings:
                selected_round = rnd
                selected_standings = standings

                try:
                    selected_matches = get_all_matches(rnd["id"])
                except Exception:
                    selected_matches = []

                break

        except Exception as exc:
            print(
                f"Could not load standings for round "
                f"{rnd.get('id')}: {exc}"
            )

    current_round = None

    if selected_round:
        current_round = selected_round.get("round_number")

    if current_round is None:
        current_round = event.get("current_round")

    players = []

    for key, tracked_player in tracked.items():
        standing = find_standing(
            selected_standings,
            tracked_player["name"],
        )

        player = normalize_player(
            tracked_player,
            standing=standing,
            matches=selected_matches,
            current_round=current_round,
        )

        players.append(player)

    event_name = (
        event.get("name")
        or event.get("title")
        or "Lorcana Event"
    )

    event_format = (
        event.get("format_name")
        or event.get("format")
        or "Core Constructed"
    )

    # Event player count should come from the actual API registration list
    # whenever possible.
    player_count = (
        len(registered_names)
        or event.get("player_count")
        or event.get("players")
        or event.get("registration_count")
        or 0
    )

    return {
        "event": {
            "id": str(EVENT_ID),
            "name": event_name,
            "format": event_format,
            "players": player_count,
            "current_round": current_round,
        },
        "last_updated": datetime.now(
            timezone.utc
        ).isoformat(),
        "players": players,
    }
