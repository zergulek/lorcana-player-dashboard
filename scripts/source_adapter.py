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
    "Accept": "application/json",
    "Referer": "https://tcg.ravensburgerplay.com/",
    "User-Agent": "Mozilla/5.0",
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


def get_items(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "results",
        "items",
        "data",
        "standings",
        "matches",
        "registrations",
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def get_player_name(obj):
    if obj is None:
        return None

    if isinstance(obj, str):
        return obj.strip()

    if not isinstance(obj, dict):
        return None

    # Direct names
    for key in (
        "display_name",
        "displayName",
        "username",
        "user_name",
        "name",
        "nickname",
    ):
        value = obj.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    # Nested player/user objects
    for key in (
        "player",
        "participant",
        "user",
        "profile",
        "player_profile",
    ):
        value = obj.get(key)

        name = get_player_name(value)

        if name:
            return name

    # First/last name fallback
    first = (
        obj.get("first_name")
        or obj.get("firstName")
    )

    last = (
        obj.get("last_name")
        or obj.get("lastName")
    )

    if first:
        if last:
            return f"{first} {last[0]}"

        return first

    return None


def get_rounds(event):
    rounds = []

    # Most common tournament structure.
    phases = event.get("tournament_phases") or []

    for phase in phases:
        for rnd in phase.get("rounds") or []:
            rounds.append(rnd)

    # Some API versions expose rounds directly.
    if not rounds:
        rounds = event.get("rounds") or []

    return rounds


def round_number(rnd):
    value = (
        rnd.get("round_number")
        or rnd.get("roundNumber")
        or rnd.get("number")
        or 0
    )

    try:
        return int(value)
    except Exception:
        return 0


def get_round_standings(round_id):
    paths = [
        f"/tournament-rounds/{round_id}/standings/paginated/",
        f"/tournament-rounds/{round_id}/standings/",
    ]

    for path in paths:
        try:
            response = api_get(
                path,
                {
                    "page": 1,
                    "page_size": 500,
                },
            )

            items = get_items(response)

            if items:
                return items

        except Exception as exc:
            print(
                f"Standings request failed: "
                f"{path}: {exc}"
            )

    return []


def get_round_matches(round_id):
    paths = [
        f"/tournament-rounds/{round_id}/matches/paginated/",
        f"/tournament-rounds/{round_id}/matches/",
    ]

    for path in paths:
        try:
            response = api_get(
                path,
                {
                    "page": 1,
                    "page_size": 500,
                },
            )

            items = get_items(response)

            if items:
                return items

        except Exception as exc:
            print(
                f"Matches request failed: "
                f"{path}: {exc}"
            )

    return []


def extract_stat(obj, *keys):
    if not isinstance(obj, dict):
        return None

    for key in keys:
        if key in obj:
            return obj[key]

    return None


def normalize_standing(item, rank_fallback):
    name = get_player_name(item)

    if not name:
        return None

    rank = extract_stat(
        item,
        "rank",
        "placement",
        "position",
    )

    points = extract_stat(
        item,
        "points",
        "match_points",
        "matchPoints",
        "total_points",
        "totalPoints",
    )

    wins = extract_stat(
        item,
        "wins",
        "match_wins",
        "matchWins",
    )

    losses = extract_stat(
        item,
        "losses",
        "match_losses",
        "matchLosses",
    )

    draws = extract_stat(
        item,
        "draws",
        "match_draws",
        "matchDraws",
    )

    game_wins = extract_stat(
        item,
        "game_wins",
        "gameWins",
    )

    game_losses = extract_stat(
        item,
        "game_losses",
        "gameLosses",
    )

    return {
        "rank": rank if rank is not None else rank_fallback,
        "name": name,
        "points": points if points is not None else 0,
        "wins": wins if wins is not None else 0,
        "losses": losses if losses is not None else 0,
        "draws": draws if draws is not None else 0,
        "game_wins": game_wins if game_wins is not None else 0,
        "game_losses": game_losses if game_losses is not None else 0,

        # Keep the original API object.
        # This is extremely useful when Ravensburger changes
        # a field name.
        "raw": item,
    }


def names_from_match(match):
    """
    Return all player names found inside a match.

    We deliberately inspect nested structures instead of
    assuming a specific player1/player2 schema.
    """

    names = []

    def walk(value, depth=0):
        if depth > 5:
            return

        if isinstance(value, dict):

            # Objects that clearly represent players.
            possible_name = get_player_name(value)

            if possible_name:
                names.append(possible_name)

            for key, child in value.items():

                key_lower = str(key).lower()

                if any(
                    word in key_lower
                    for word in (
                        "player",
                        "participant",
                        "opponent",
                        "user",
                    )
                ):
                    walk(child, depth + 1)

        elif isinstance(value, list):
            for child in value:
                walk(child, depth + 1)

    walk(match)

    # Remove duplicates.
    result = []

    for name in names:
        if name not in result:
            result.append(name)

    return result


def normalize_match(match, round_id, round_no):
    players = names_from_match(match)

    return {
        "round_id": round_id,
        "round": round_no,
        "players": players,
        "raw": match,
    }


def load_tracked_players():
    if not DATA_FILE.exists():
        return []

    try:
        data = json.loads(
            DATA_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return []

    return data.get("players", [])


def get_fresh_data():

    print(
        f"Loading Ravensburger event {EVENT_ID}"
    )

    event = api_get(
        f"/events/{EVENT_ID}/"
    )

    rounds = get_rounds(event)

    rounds = sorted(
        rounds,
        key=round_number,
    )

    all_round_data = []

    for rnd in rounds:

        rid = rnd.get("id")

        if not rid:
            continue

        rno = round_number(rnd)

        print(
            f"Loading round {rno} "
            f"(id={rid})"
        )

        standings = get_round_standings(rid)

        matches = get_round_matches(rid)

        all_round_data.append(
            {
                "id": rid,
                "round": rno,
                "standings": [
                    normalize_standing(
                        item,
                        index + 1,
                    )
                    for index, item in enumerate(
                        standings
                    )
                    if normalize_standing(
                        item,
                        index + 1,
                    )
                ],
                "matches": [
                    normalize_match(
                        item,
                        rid,
                        rno,
                    )
                    for item in matches
                ],
            }
        )

    # Latest round containing standings.
    latest = None

    for rnd in reversed(all_round_data):
        if rnd["standings"]:
            latest = rnd
            break

    if latest is None and all_round_data:
        latest = all_round_data[-1]

    tracked = load_tracked_players()

    tracked_names = {
        p.get("name", "").lower()
        for p in tracked
    }

    # Build tracked player data.
    players = []

    if latest:

        for tracked_player in tracked:

            target = tracked_player.get(
                "name",
                "",
            ).lower()

            standing = next(
                (
                    s
                    for s in latest["standings"]
                    if s["name"].lower() == target
                ),
                None,
            )

            player = {
                "name": tracked_player.get(
                    "name",
                    "",
                ),
                "tag": tracked_player.get(
                    "tag",
                    "",
                ),
                "rank": (
                    standing["rank"]
                    if standing
                    else None
                ),
                "points": (
                    standing["points"]
                    if standing
                    else 0
                ),
                "match_wins": (
                    standing["wins"]
                    if standing
                    else 0
                ),
                "match_losses": (
                    standing["losses"]
                    if standing
                    else 0
                ),
                "game_wins": (
                    standing["game_wins"]
                    if standing
                    else 0
                ),
                "game_losses": (
                    standing["game_losses"]
                    if standing
                    else 0
                ),
                "status": "active",
                "matches": [],
            }

            # Find all matches involving this player.
            for rnd in all_round_data:

                for match in rnd["matches"]:

                    names = [
                        n.lower()
                        for n in match["players"]
                    ]

                    if target not in names:
                        continue

                    opponents = [
                        n
                        for n in match["players"]
                        if n.lower() != target
                    ]

                    raw = match["raw"]

                    # Try to find a result.
                    result = "—"

                    raw_text = json.dumps(
                        raw,
                        ensure_ascii=False,
                    ).lower()

                    if (
                        '"result": "win"' in raw_text
                        or '"result":"win"' in raw_text
                        or '"winner": true' in raw_text
                    ):
                        result = "W"

                    elif (
                        '"result": "loss"' in raw_text
                        or '"result":"loss"' in raw_text
                        or '"winner": false' in raw_text
                    ):
                        result = "L"

                    player["matches"].append(
                        {
                            "round": match["round"],
                            "opponent": (
                                opponents[0]
                                if opponents
                                else "—"
                            ),
                            "result": result,
                            "score": (
                                extract_stat(
                                    raw,
                                    "score",
                                    "game_score",
                                    "gameScore",
                                )
                                or "—"
                            ),
                            "table": (
                                extract_stat(
                                    raw,
                                    "table",
                                    "table_number",
                                    "tableNumber",
                                )
                                or "—"
                            ),
                        }
                    )

            players.append(player)

    # All participants = latest standings.
    all_standings = (
        latest["standings"]
        if latest
        else []
    )

    return {
        "event": {
            "id": str(EVENT_ID),
            "name": (
                event.get("name")
                or event.get("title")
                or "Lorcana Event"
            ),
            "format": (
                event.get("format_name")
                or event.get("format")
                or "Core Constructed"
            ),
            "players": len(
                all_standings
            ),
            "current_round": (
                latest["round"]
                if latest
                else None
            ),
        },

        "last_updated": datetime.now(
            timezone.utc
        ).isoformat(),

        "players": players,

        "standings": all_standings,

        "rounds": all_round_data,
    }
