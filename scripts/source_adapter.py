from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import requests


BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "event.json"

API_BASE = "https://api.cloudflare.ravensburgerplay.com/hydraproxy/api/v2"
EVENT_ID = os.getenv("EVENT_ID", "1007231")

HEADERS = {
    "Accept": "application/json",
    "Referer": "https://tcg.ravensburgerplay.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
}

TIMEOUT = 30


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def api_get(path, params=None):
    url = f"{API_BASE}{path}"

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=TIMEOUT,
    )

    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def get_items(data):
    """
    Ravensburger endpoints don't all return exactly the same structure.

    Accept:
      - list
      - results
      - items
      - data
      - standings
      - matches
      - registrations
    """

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

        if isinstance(value, dict):
            nested = get_items(value)
            if nested:
                return nested

    return []


def first_nonempty(*values):
    for value in values:
        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue

        return value

    return None


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


# ---------------------------------------------------------------------------
# Player name handling
# ---------------------------------------------------------------------------

def clean_player_identifier(value):
    """
    Convert Ravensburger identifiers into a form that can be compared
    with the tracked names in data/event.json.

    Examples:

      "[OSA] Moluk"       -> "Moluk"
      "[OSA] Moluk 🇵🇱"   -> "Moluk"
      "Moluk"             -> "Moluk"
    """

    value = clean_text(value)

    if not value:
        return ""

    # Remove team/tag prefix such as [OSA]
    value = re.sub(r"^\s*\[[^\]]+\]\s*", "", value)

    # Remove common Discord-style emoji suffixes.
    # Keep normal letters/numbers and spaces.
    value = re.sub(
        r"[\U00010000-\U0010ffff]+",
        "",
        value,
    )

    # Normalize whitespace.
    value = re.sub(r"\s+", " ", value).strip()

    return value


def normalize_name_for_match(value):
    """
    Produce a forgiving comparison key.

    This allows:
      Moluk
      moluk
      [OSA] Moluk
      Moluk 🇵🇱

    to match one another.
    """

    value = clean_player_identifier(value)

    value = value.casefold()

    # Remove remaining non-alphanumeric characters while keeping
    # Unicode letters/numbers.
    value = "".join(
        char
        for char in value
        if char.isalnum() or char.isspace()
    )

    value = re.sub(r"\s+", " ", value).strip()

    return value


def get_player_name(item):
    """
    Extract the most useful player identifier from a standings object.

    IMPORTANT:
    The current Ravensburger API places the display name we need under:

        user_event_status.best_identifier

    Example:

        user_event_status.best_identifier = "[OSA] Moluk..."
    """

    if not isinstance(item, dict):
        return ""

    user_event_status = item.get("user_event_status") or {}

    # This is the most important current API field.
    candidates = [
        user_event_status.get("best_identifier"),
        user_event_status.get("display_name"),
        user_event_status.get("displayName"),

        item.get("best_identifier"),
        item.get("display_name"),
        item.get("displayName"),
        item.get("username"),
        item.get("user_name"),
        item.get("nickname"),
        item.get("name"),
    ]

    # Nested player object.
    player = item.get("player")

    if isinstance(player, dict):
        candidates.extend([
            player.get("best_identifier"),
            player.get("display_name"),
            player.get("displayName"),
            player.get("username"),
            player.get("user_name"),
            player.get("nickname"),
            player.get("name"),
        ])

    # Nested user object.
    user = item.get("user")

    if isinstance(user, dict):
        candidates.extend([
            user.get("best_identifier"),
            user.get("display_name"),
            user.get("displayName"),
            user.get("username"),
            user.get("user_name"),
            user.get("nickname"),
            user.get("name"),
        ])

    for candidate in candidates:
        if candidate:
            return clean_player_identifier(candidate)

    return ""


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def get_int(*values, default=0):
    for value in values:
        if value is None:
            continue

        try:
            return int(value)
        except (TypeError, ValueError):
            continue

    return default


def get_float(*values, default=0.0):
    for value in values:
        if value is None:
            continue

        try:
            return float(value)
        except (TypeError, ValueError):
            continue

    return default


# ---------------------------------------------------------------------------
# Event / round handling
# ---------------------------------------------------------------------------

def get_rounds(event):
    rounds = []

    if not isinstance(event, dict):
        return rounds

    phases = event.get("tournament_phases")

    if isinstance(phases, list):
        for phase in phases:
            if not isinstance(phase, dict):
                continue

            phase_rounds = phase.get("rounds")

            if isinstance(phase_rounds, list):
                rounds.extend(phase_rounds)

    if rounds:
        return rounds

    direct_rounds = event.get("rounds")

    if isinstance(direct_rounds, list):
        return direct_rounds

    return []


def round_number(round_data):
    if not isinstance(round_data, dict):
        return 0

    return get_int(
        round_data.get("round_number"),
        round_data.get("roundNumber"),
        round_data.get("number"),
        default=0,
    )


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------

def get_round_standings(round_id):
    """
    Retrieve standings for a tournament round.

    The current API returns:

        {
          "standings": [...]
        }

    Try both known endpoint variants.
    """

    endpoints = [
        f"/tournament-rounds/{round_id}/standings/paginated/",
        f"/tournament-rounds/{round_id}/standings/",
    ]

    for endpoint in endpoints:
        try:
            data = api_get(
                endpoint,
                params={
                    "page": 1,
                    "page_size": 500,
                },
            )

            items = get_items(data)

            if items:
                print(
                    f"Standings loaded: round={round_id}, "
                    f"count={len(items)}, endpoint={endpoint}"
                )
                return items

            print(
                f"Standings endpoint returned no items: "
                f"round={round_id}, endpoint={endpoint}"
            )

        except Exception as exc:
            print(
                f"Standings request failed: "
                f"round={round_id}, endpoint={endpoint}, "
                f"error={repr(exc)}"
            )

    return []


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

def get_round_matches(round_id):
    endpoints = [
        f"/tournament-rounds/{round_id}/matches/paginated/",
        f"/tournament-rounds/{round_id}/matches/",
    ]

    for endpoint in endpoints:
        try:
            data = api_get(
                endpoint,
                params={
                    "page": 1,
                    "page_size": 500,
                },
            )

            items = get_items(data)

            if items:
                print(
                    f"Matches loaded: round={round_id}, "
                    f"count={len(items)}, endpoint={endpoint}"
                )
                return items

        except Exception as exc:
            print(
                f"Matches request failed: "
                f"round={round_id}, endpoint={endpoint}, "
                f"error={repr(exc)}"
            )

    return []


# ---------------------------------------------------------------------------
# Standing normalization
# ---------------------------------------------------------------------------

def normalize_standing(item, fallback_rank=0):
    if not isinstance(item, dict):
        return None

    user_event_status = item.get("user_event_status") or {}

    player = item.get("player") or {}

    name = get_player_name(item)

    if not name:
        return None

    rank = get_int(
        item.get("rank"),
        default=fallback_rank,
    )

    # Current API:
    #
    # user_event_status.matches_won
    # user_event_status.matches_drawn
    # user_event_status.matches_lost
    # user_event_status.total_match_points
    #
    # It also exposes points directly on the standing object.

    wins = get_int(
        user_event_status.get("matches_won"),
        item.get("wins"),
        item.get("match_wins"),
        item.get("matchWins"),
        default=0,
    )

    draws = get_int(
        user_event_status.get("matches_drawn"),
        item.get("draws"),
        item.get("match_draws"),
        item.get("matchDraws"),
        default=0,
    )

    losses = get_int(
        user_event_status.get("matches_lost"),
        item.get("losses"),
        item.get("match_losses"),
        item.get("matchLosses"),
        default=0,
    )

    points = get_int(
        item.get("points"),
        item.get("match_points"),
        user_event_status.get("total_match_points"),
        default=0,
    )

    # The current API exposes these as percentages.
    game_win_percentage = get_float(
        item.get("game_win_percentage"),
        item.get("gameWinPercentage"),
        default=0.0,
    )

    opponent_game_win_percentage = get_float(
        item.get("opponent_game_win_percentage"),
        item.get("opponentGameWinPercentage"),
        default=0.0,
    )

    opponent_match_win_percentage = get_float(
        item.get("opponent_match_win_percentage"),
        item.get("opponentMatchWinPercentage"),
        default=0.0,
    )

    # We don't currently have explicit game win/loss totals in the
    # standings object. Leave these as zero until match-level data
    # provides them.
    game_wins = get_int(
        item.get("game_wins"),
        item.get("gameWins"),
        default=0,
    )

    game_losses = get_int(
        item.get("game_losses"),
        item.get("gameLosses"),
        default=0,
    )

    return {
        "name": name,
        "player_id": player.get("id") or item.get("id"),
        "rank": rank,
        "points": points,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "game_wins": game_wins,
        "game_losses": game_losses,
        "game_win_percentage": game_win_percentage,
        "opponent_game_win_percentage": opponent_game_win_percentage,
        "opponent_match_win_percentage": opponent_match_win_percentage,
        "record": item.get("record"),
        "match_record": item.get("match_record"),
    }


# ---------------------------------------------------------------------------
# Match normalization
# ---------------------------------------------------------------------------

def extract_match_player_names(item):
    names = []

    if not isinstance(item, dict):
        return names

    # Common direct fields.
    for key in (
        "player",
        "player1",
        "player2",
        "opponent",
        "opponent_player",
        "winner",
        "loser",
    ):
        value = item.get(key)

        if isinstance(value, dict):
            name = first_nonempty(
                value.get("best_identifier"),
                value.get("display_name"),
                value.get("displayName"),
                value.get("username"),
                value.get("name"),
            )

            if name:
                names.append(clean_player_identifier(name))

        elif isinstance(value, str):
            names.append(clean_player_identifier(value))

    # Some APIs nest participants.
    for key in (
        "players",
        "participants",
        "match_players",
    ):
        value = item.get(key)

        if isinstance(value, list):
            for participant in value:
                if isinstance(participant, dict):
                    name = first_nonempty(
                        participant.get("best_identifier"),
                        participant.get("display_name"),
                        participant.get("displayName"),
                        participant.get("username"),
                        participant.get("name"),
                    )

                    if name:
                        names.append(clean_player_identifier(name))

    return list(dict.fromkeys(
        name for name in names if name
    ))


def normalize_match(item, round_id, round_no):
    if not isinstance(item, dict):
        return None

    return {
        "id": item.get("id"),
        "round_id": round_id,
        "round": round_no,
        "players": extract_match_player_names(item),
        "raw": item,
    }


# ---------------------------------------------------------------------------
# Tracked players
# ---------------------------------------------------------------------------

def load_tracked_players():
    """
    Load the 23 tracked players from data/event.json.
    """

    if not DATA.exists():
        print(f"Tracked-player data file does not exist: {DATA}")
        return []

    data = json.loads(
        DATA.read_text(encoding="utf-8")
    )

    players = data.get("players", [])

    if not isinstance(players, list):
        return []

    return players


# ---------------------------------------------------------------------------
# Player matching
# ---------------------------------------------------------------------------

def find_standing_for_player(tracked_player, standings):
    tracked_name = normalize_name_for_match(
        tracked_player.get("name", "")
    )

    if not tracked_name:
        return None

    # Exact normalized name match.
    for standing in standings:
        standing_name = normalize_name_for_match(
            standing.get("name", "")
        )

        if standing_name == tracked_name:
            return standing

    # Second attempt:
    # Compare the tracked name against the raw API identifiers.
    #
    # This helps with cases such as:
    #   tracked = "Moluk"
    #   API     = "[OSA] Moluk"
    for standing in standings:
        api_name = normalize_name_for_match(
            standing.get("name", "")
        )

        if tracked_name in api_name or api_name in tracked_name:
            return standing

    return None


# ---------------------------------------------------------------------------
# Main data loader
# ---------------------------------------------------------------------------

def get_fresh_data():
    print(f"Loading Ravensburger event {EVENT_ID}")

    event = api_get(
        f"/events/{EVENT_ID}/"
    )

    rounds = get_rounds(event)

    print(f"Rounds discovered: {len(rounds)}")

    rounds = sorted(
        rounds,
        key=round_number,
    )

    all_round_data = []

    for rnd in rounds:
        if not isinstance(rnd, dict):
            continue

        rid = rnd.get("id")

        if not rid:
            continue

        rno = round_number(rnd)

        print(
            f"Loading round {rno} "
            f"(id={rid})"
        )

        standings_raw = get_round_standings(rid)
        matches_raw = get_round_matches(rid)

        standings = []

        for index, item in enumerate(
            standings_raw,
            start=1,
        ):
            normalized = normalize_standing(
                item,
                index,
            )

            if normalized:
                standings.append(normalized)

        matches = []

        for item in matches_raw:
            normalized = normalize_match(
                item,
                rid,
                rno,
            )

            if normalized:
                matches.append(normalized)

        all_round_data.append({
            "id": rid,
            "round": rno,
            "standings": standings,
            "matches": matches,
        })

        print(
            f"Round {rno}: "
            f"{len(standings)} standings, "
            f"{len(matches)} matches"
        )

    # Prefer the latest round that actually has standings.
    latest = None

    for rnd in reversed(all_round_data):
        if rnd.get("standings"):
            latest = rnd
            break

    # If no standings exist, keep the latest round object
    # so tracked players can still be displayed.
    if latest is None and all_round_data:
        latest = all_round_data[-1]

    tracked = load_tracked_players()

    print(
        f"Tracked players loaded: {len(tracked)}"
    )

    players = []

    if latest:
        standings = latest.get("standings", [])

        for tracked_player in tracked:
            standing = find_standing_for_player(
                tracked_player,
                standings,
            )

            player = {
                "name": tracked_player.get("name", ""),
                "tag": tracked_player.get("tag", ""),
                "rank": (
                    standing["rank"]
                    if standing
                    else None
                ),
                "points": (
                    standing["points"]
                    if standing
                    else None
                ),
                "match_wins": (
                    standing["wins"]
                    if standing
                    else None
                ),
                "match_draws": (
                    standing["draws"]
                    if standing
                    else None
                ),
                "match_losses": (
                    standing["losses"]
                    if standing
                    else None
                ),
                "game_wins": (
                    standing["game_wins"]
                    if standing
                    else None
                ),
                "game_losses": (
                    standing["game_losses"]
                    if standing
                    else None
                ),
                "opponent": "—",
                "status": "active",
                "matches": [],
            }

            # Try to find this player's latest match.
            player_key = normalize_name_for_match(
                tracked_player.get("name", "")
            )

            for match in latest.get("matches", []):
                match_names = [
                    normalize_name_for_match(name)
                    for name in match.get("players", [])
                ]

                if player_key in match_names:
                    player["matches"].append(match)

                    # If we can identify another player in
                    # the match, expose them as opponent.
                    opponents = [
                        name
                        for name in match.get("players", [])
                        if normalize_name_for_match(name)
                        != player_key
                    ]

                    if opponents:
                        player["opponent"] = opponents[0]

            players.append(player)

    all_standings = (
        latest.get("standings", [])
        if latest
        else []
    )

    # Event participant count should come from the event itself
    # whenever available, rather than len(tracked standings).
    event_player_count = first_nonempty(
        event.get("players"),
        event.get("player_count"),
        event.get("participant_count"),
    )

    if isinstance(event_player_count, dict):
        event_player_count = first_nonempty(
            event_player_count.get("count"),
            event_player_count.get("total"),
        )

    event_player_count = get_int(
        event_player_count,
        default=len(all_standings),
    )

    current_round = (
        latest.get("round")
        if latest
        else None
    )

    result = {
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
            "players": event_player_count,
            "current_round": current_round,
        },
        "last_updated": datetime.now(
            timezone.utc
        ).isoformat(),
        "players": players,
        "standings": all_standings,
        "rounds": all_round_data,
    }

    # Helpful deployment diagnostics.
    matched_count = sum(
        1
        for player in players
        if player.get("rank") is not None
    )

    print(
        f"RESULT: participants={event_player_count}, "
        f"tracked={len(players)}, "
        f"matched={matched_count}, "
        f"standings={len(all_standings)}, "
        f"round={current_round}"
    )

    return result


# ---------------------------------------------------------------------------
# Static refresh command
# ---------------------------------------------------------------------------

def main():
    data = get_fresh_data()

    DATA.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        f"Updated {DATA}"
    )


if __name__ == "__main__":
    main()
