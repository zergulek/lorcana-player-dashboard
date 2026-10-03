from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import unicodedata

import requests


# ============================================================================
# CONFIG
# ============================================================================

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


# ============================================================================
# HTTP
# ============================================================================

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


# ============================================================================
# GENERIC HELPERS
# ============================================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


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


def get_int(*values, default=0):
    for value in values:
        if value is None:
            continue

        try:
            return int(value)
        except (TypeError, ValueError):
            pass

    return default


def get_float(*values, default=0.0):
    for value in values:
        if value is None:
            continue

        try:
            return float(value)
        except (TypeError, ValueError):
            pass

    return default


def get_items(data):
    """
    Normalize different API response formats.

    Supports:
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


# ============================================================================
# PLAYER NAME HANDLING
# ============================================================================

def repair_mojibake(value):
    """
    Ravensburger data can occasionally contain incorrectly decoded UTF-8
    fragments, for example:

        Molukðµð±ðï¸

    We don't need to perfectly reconstruct the emoji.

    The important part is preserving the actual nickname:
        Moluk
    """

    value = clean_text(value)

    if not value:
        return ""

    # Remove characters that are commonly produced by broken UTF-8 emoji
    # decoding. This intentionally leaves normal letters/numbers intact.
    value = re.sub(
        r"[\u00D0\u00D1][\u0080-\u00BF]+",
        "",
        value,
    )

    return value


def clean_player_identifier(value):
    """
    Convert Ravensburger player identifiers into a comparable form.

    Examples:

        "[OSA] Moluk"
            -> "Moluk"

        "[OSA] Moluk 🇵🇱"
            -> "Moluk"

        "Molukðµð±ðï¸"
            -> "Moluk"
    """

    value = clean_text(value)

    if not value:
        return ""

    # Remove team/tag prefix.
    #
    # [OSA] Moluk
    # [Q2W] EvilBunny
    # [GPL] Hitorit
    value = re.sub(
        r"^\s*\[[^\]]+\]\s*",
        "",
        value,
    )

    # Try to remove malformed UTF-8 fragments.
    value = repair_mojibake(value)

    # Remove normal emoji / supplementary Unicode characters.
    value = re.sub(
        r"[\U00010000-\U0010FFFF]+",
        "",
        value,
    )

    # Normalize Unicode.
    value = unicodedata.normalize(
        "NFKC",
        value,
    )

    # Normalize whitespace.
    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def normalize_name_for_match(value):
    """
    Produce a forgiving comparison key.

    Examples:

        Moluk
        moluk
        [OSA] Moluk
        Moluk 🇵🇱

    all become comparable.

    We deliberately do NOT require the API name to be an exact string.
    """

    value = clean_player_identifier(value)

    if not value:
        return ""

    value = value.casefold()

    # Keep Unicode letters and numbers.
    value = "".join(
        char
        for char in value
        if char.isalnum() or char.isspace()
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def get_player_name(item):
    """
    Extract the actual tournament display name.

    IMPORTANT:
    Current Ravensburger API frequently stores the tournament nickname in:

        user_event_status.best_identifier

    while:

        player.best_identifier

    can contain a completely different account/legal/display name.

    Therefore user_event_status.best_identifier has priority.
    """

    if not isinstance(item, dict):
        return ""

    user_event_status = item.get("user_event_status") or {}

    candidates = [
        # CURRENT / MOST IMPORTANT
        user_event_status.get("best_identifier"),
        user_event_status.get("display_name"),
        user_event_status.get("displayName"),

        # Direct standing fields
        item.get("best_identifier"),
        item.get("display_name"),
        item.get("displayName"),
        item.get("username"),
        item.get("user_name"),
        item.get("nickname"),
        item.get("name"),
    ]

    # Nested player.
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

    # Nested user.
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
            cleaned = clean_player_identifier(candidate)

            if cleaned:
                return cleaned

    return ""


# ============================================================================
# EVENT / ROUND HANDLING
# ============================================================================

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


# ============================================================================
# STANDINGS
# ============================================================================

def get_round_standings(round_id):
    """
    Current endpoint:

        /tournament-rounds/{round_id}/standings/

    Try paginated endpoint first, then normal endpoint.
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
                    f"Standings loaded: "
                    f"round={round_id}, "
                    f"count={len(items)}, "
                    f"endpoint={endpoint}"
                )

                return items

            print(
                f"Standings endpoint returned no items: "
                f"round={round_id}, "
                f"endpoint={endpoint}"
            )

        except Exception as exc:
            print(
                f"Standings request failed: "
                f"round={round_id}, "
                f"endpoint={endpoint}, "
                f"error={repr(exc)}"
            )

    return []


# ============================================================================
# MATCHES
# ============================================================================

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
                    f"Matches loaded: "
                    f"round={round_id}, "
                    f"count={len(items)}, "
                    f"endpoint={endpoint}"
                )

                return items

        except Exception as exc:
            print(
                f"Matches request failed: "
                f"round={round_id}, "
                f"endpoint={endpoint}, "
                f"error={repr(exc)}"
            )

    return []


# ============================================================================
# STANDING NORMALIZATION
# ============================================================================

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

    # ------------------------------------------------------------------------
    # MATCH RESULTS
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # POINTS
    # ------------------------------------------------------------------------

    points = get_int(
        item.get("points"),
        item.get("match_points"),
        user_event_status.get("total_match_points"),
        default=0,
    )

    # ------------------------------------------------------------------------
    # GAME STATISTICS
    # ------------------------------------------------------------------------

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
        "player_id": (
            player.get("id")
            or item.get("id")
        ),
        "rank": rank,
        "points": points,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "game_wins": game_wins,
        "game_losses": game_losses,
        "game_win_percentage": game_win_percentage,
        "opponent_game_win_percentage": (
            opponent_game_win_percentage
        ),
        "opponent_match_win_percentage": (
            opponent_match_win_percentage
        ),
        "record": item.get("record"),
        "match_record": item.get("match_record"),
    }


# ============================================================================
# MATCH NORMALIZATION
# ============================================================================

def extract_name_from_match_object(value):
    if isinstance(value, str):
        return clean_player_identifier(value)

    if not isinstance(value, dict):
        return ""

    # Some match endpoints can use user_event_status too.
    status = value.get("user_event_status")

    if isinstance(status, dict):
        name = first_nonempty(
            status.get("best_identifier"),
            status.get("display_name"),
            status.get("displayName"),
        )

        if name:
            return clean_player_identifier(name)

    name = first_nonempty(
        value.get("best_identifier"),
        value.get("display_name"),
        value.get("displayName"),
        value.get("username"),
        value.get("user_name"),
        value.get("nickname"),
        value.get("name"),
    )

    if name:
        return clean_player_identifier(name)

    # Nested player.
    player = value.get("player")

    if isinstance(player, dict):
        name = first_nonempty(
            player.get("best_identifier"),
            player.get("display_name"),
            player.get("displayName"),
            player.get("username"),
            player.get("name"),
        )

        if name:
            return clean_player_identifier(name)

    return ""


def extract_match_player_names(item):
    names = []

    if not isinstance(item, dict):
        return names

    # Direct player fields.
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

        name = extract_name_from_match_object(value)

        if name:
            names.append(name)

    # Lists.
    for key in (
        "players",
        "participants",
        "match_players",
    ):
        value = item.get(key)

        if isinstance(value, list):
            for participant in value:
                name = extract_name_from_match_object(
                    participant
                )

                if name:
                    names.append(name)

    # Remove duplicates.
    return list(
        dict.fromkeys(
            name
            for name in names
            if name
        )
    )


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


# ============================================================================
# TRACKED PLAYERS
# ============================================================================

def load_tracked_players():
    """
    Load tracked players from data/event.json.
    """

    if not DATA.exists():
        print(
            f"Tracked-player data file does not exist: {DATA}"
        )

        return []

    try:
        data = json.loads(
            DATA.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        print(
            f"Could not read tracked players: "
            f"{repr(exc)}"
        )

        return []

    players = data.get("players", [])

    if not isinstance(players, list):
        return []

    return players


# ============================================================================
# PLAYER MATCHING
# ============================================================================

def get_possible_tracked_names(tracked_player):
    """
    Build several possible identifiers.

    Usually this is just the player's name.

    We also keep the tag because it can help distinguish
    duplicate nicknames.
    """

    if not isinstance(tracked_player, dict):
        return []

    names = []

    player_name = tracked_player.get("name")

    if player_name:
        names.append(
            normalize_name_for_match(
                player_name
            )
        )

    # Some source files may contain an alternate name.
    for key in (
        "username",
        "nickname",
        "display_name",
        "displayName",
    ):
        value = tracked_player.get(key)

        if value:
            names.append(
                normalize_name_for_match(value)
            )

    return list(
        dict.fromkeys(
            name
            for name in names
            if name
        )
    )


def find_standing_for_player(
    tracked_player,
    standings,
):
    """
    Match a tracked player against API standings.

    Matching order:

    1. Exact normalized nickname.
    2. API identifier contains tracked nickname.
    3. Tracked nickname contains API identifier.
    4. Token/prefix comparison.

    This is intentionally tolerant of Ravensburger's malformed
    Unicode identifiers.
    """

    tracked_names = get_possible_tracked_names(
        tracked_player
    )

    if not tracked_names:
        return None

    # ------------------------------------------------------------------------
    # PASS 1: EXACT
    # ------------------------------------------------------------------------

    for standing in standings:
        standing_name = normalize_name_for_match(
            standing.get("name", "")
        )

        if not standing_name:
            continue

        for tracked_name in tracked_names:
            if standing_name == tracked_name:
                return standing

    # ------------------------------------------------------------------------
    # PASS 2: CONTAINS
    #
    # Example:
    #
    # tracked:
    #     Moluk
    #
    # API:
    #     Molukðµð±ðï¸
    #
    # ------------------------------------------------------------------------

    for standing in standings:
        standing_name = normalize_name_for_match(
            standing.get("name", "")
        )

        if not standing_name:
            continue

        for tracked_name in tracked_names:
            if (
                len(tracked_name) >= 4
                and tracked_name in standing_name
            ):
                return standing

    # ------------------------------------------------------------------------
    # PASS 3: REVERSE CONTAINS
    # ------------------------------------------------------------------------

    for standing in standings:
        standing_name = normalize_name_for_match(
            standing.get("name", "")
        )

        if not standing_name:
            continue

        for tracked_name in tracked_names:
            if (
                len(standing_name) >= 4
                and standing_name in tracked_name
            ):
                return standing

    # ------------------------------------------------------------------------
    # PASS 4: PREFIX / TOKEN
    #
    # Helps with small encoding or suffix differences.
    # ------------------------------------------------------------------------

    for standing in standings:
        standing_name = normalize_name_for_match(
            standing.get("name", "")
        )

        if not standing_name:
            continue

        for tracked_name in tracked_names:
            tracked_compact = tracked_name.replace(
                " ",
                "",
            )

            standing_compact = standing_name.replace(
                " ",
                "",
            )

            if len(tracked_compact) >= 5:
                if (
                    tracked_compact.startswith(
                        standing_compact
                    )
                    or standing_compact.startswith(
                        tracked_compact
                    )
                ):
                    return standing

    return None


# ============================================================================
# MATCH LOOKUP
# ============================================================================

def find_matches_for_player(
    tracked_player,
    matches,
):
    player_name = normalize_name_for_match(
        tracked_player.get("name", "")
    )

    if not player_name:
        return []

    result = []

    for match in matches:
        names = [
            normalize_name_for_match(name)
            for name in match.get("players", [])
        ]

        if not names:
            continue

        found = False

        for name in names:
            if name == player_name:
                found = True
                break

            if (
                len(player_name) >= 4
                and player_name in name
            ):
                found = True
                break

            if (
                len(name) >= 4
                and name in player_name
            ):
                found = True
                break

        if found:
            result.append(match)

    return result


def find_opponent(
    tracked_player,
    matches,
):
    player_name = normalize_name_for_match(
        tracked_player.get("name", "")
    )

    if not player_name:
        return "—"

    player_matches = find_matches_for_player(
        tracked_player,
        matches,
    )

    # Use latest match involving this player.
    for match in reversed(player_matches):
        for name in match.get("players", []):
            normalized = normalize_name_for_match(
                name
            )

            if not normalized:
                continue

            if normalized == player_name:
                continue

            if (
                player_name in normalized
                or normalized in player_name
            ):
                continue

            return name

    return "—"


# ============================================================================
# MAIN DATA LOADER
# ============================================================================

def get_fresh_data():
    print(
        f"Loading Ravensburger event {EVENT_ID}"
    )

    # ------------------------------------------------------------------------
    # EVENT
    # ------------------------------------------------------------------------

    event = api_get(
        f"/events/{EVENT_ID}/"
    )

    # ------------------------------------------------------------------------
    # ROUNDS
    # ------------------------------------------------------------------------

    rounds = get_rounds(event)

    print(
        f"Rounds discovered: {len(rounds)}"
    )

    rounds = sorted(
        rounds,
        key=round_number,
    )

    all_round_data = []

    # ------------------------------------------------------------------------
    # LOAD EACH ROUND
    # ------------------------------------------------------------------------

    for rnd in rounds:
        if not isinstance(rnd, dict):
            continue

        round_id = rnd.get("id")

        if not round_id:
            continue

        round_no = round_number(rnd)

        print(
            f"Loading round {round_no} "
            f"(id={round_id})"
        )

        standings_raw = get_round_standings(
            round_id
        )

        matches_raw = get_round_matches(
            round_id
        )

        # ------------------------------------------------------------
        # Normalize standings.
        # ------------------------------------------------------------

        standings = []

        for index, item in enumerate(
            standings_raw,
            start=1,
        ):
            normalized = normalize_standing(
                item,
                fallback_rank=index,
            )

            if normalized:
                standings.append(
                    normalized
                )

        # ------------------------------------------------------------
        # Normalize matches.
        # ------------------------------------------------------------

        matches = []

        for item in matches_raw:
            normalized = normalize_match(
                item,
                round_id,
                round_no,
            )

            if normalized:
                matches.append(
                    normalized
                )

        all_round_data.append(
            {
                "id": round_id,
                "round": round_no,
                "standings": standings,
                "matches": matches,
            }
        )

        print(
            f"Round {round_no}: "
            f"{len(standings)} standings, "
            f"{len(matches)} matches"
        )

    # =========================================================================
    # SELECT CURRENT / LATEST ROUND
    # =========================================================================

    latest = None

    # Prefer the highest-numbered round that has standings.
    for rnd in reversed(all_round_data):
        if rnd.get("standings"):
            latest = rnd
            break

    # If no standings exist, retain latest round.
    if latest is None and all_round_data:
        latest = all_round_data[-1]

    # =========================================================================
    # TRACKED PLAYERS
    # =========================================================================

    tracked = load_tracked_players()

    print(
        f"Tracked players loaded: {len(tracked)}"
    )

    players = []

    latest_standings = (
        latest.get("standings", [])
        if latest
        else []
    )

    latest_matches = (
        latest.get("matches", [])
        if latest
        else []
    )

    # =========================================================================
    # MATCH TRACKED PLAYERS
    # =========================================================================

    for tracked_player in tracked:
        standing = find_standing_for_player(
            tracked_player,
            latest_standings,
        )

        matches = find_matches_for_player(
            tracked_player,
            latest_matches,
        )

        opponent = find_opponent(
            tracked_player,
            latest_matches,
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

            "opponent": opponent,

            "status": "active",

            "matches": matches,
        }

        players.append(player)

    # =========================================================================
    # EVENT PLAYER COUNT
    # =========================================================================

    event_player_count = first_nonempty(
        event.get("players"),
        event.get("player_count"),
        event.get("participant_count"),
    )

    if isinstance(
        event_player_count,
        dict,
    ):
        event_player_count = first_nonempty(
            event_player_count.get(
                "count"
            ),
            event_player_count.get(
                "total"
            ),
        )

    event_player_count = get_int(
        event_player_count,
        default=len(latest_standings),
    )

    # =========================================================================
    # CURRENT ROUND
    # =========================================================================

    current_round = (
        latest.get("round")
        if latest
        else None
    )

    # =========================================================================
    # RESULT
    # =========================================================================

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

        "standings": latest_standings,

        "rounds": all_round_data,
    }

    # =========================================================================
    # DIAGNOSTICS
    # =========================================================================

    matched_count = sum(
        1
        for player in players
        if player.get("rank") is not None
    )

    print(
        "RESULT: "
        f"participants={event_player_count}, "
        f"tracked={len(players)}, "
        f"matched={matched_count}, "
        f"standings={len(latest_standings)}, "
        f"round={current_round}"
    )

    # Print unmatched players explicitly.
    unmatched = [
        player.get("name", "")
        for player in players
        if player.get("rank") is None
    ]

    if unmatched:
        print(
            "UNMATCHED PLAYERS: "
            + ", ".join(unmatched)
        )

    # Print matched players explicitly.
    matched = [
        (
            player.get("name", ""),
            player.get("rank"),
            player.get("points"),
            player.get("match_wins"),
            player.get("match_losses"),
        )
        for player in players
        if player.get("rank") is not None
    ]

    if matched:
        print(
            "MATCHED PLAYERS:"
        )

        for (
            name,
            rank,
            points,
            wins,
            losses,
        ) in matched:
            print(
                f"  {name}: "
                f"rank={rank}, "
                f"points={points}, "
                f"record={wins}-{losses}"
            )

    return result


# ============================================================================
# STATIC REFRESH COMMAND
# ============================================================================

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
    main()from pathlib import Path
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
