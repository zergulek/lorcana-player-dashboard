# Adapter for your existing Ravensburger scraper.
# Return data in the normalized structure described in README.md.
#
# Example:
# from pathlib import Path
# import json
#
# def load_from_existing_scraper():
#     raw = json.loads(
#         Path("raw/event_1007231.json").read_text()
#     )
#     ...
#     return normalized
#
# Keep this module free of credentials.
# If the source needs authentication,
# use environment variables and document them in README.md.import json
import os
from pathlib import Path
from datetime import datetime, timezone

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

    print("=" * 80)
    print("REQUEST:", url)
    print("PARAMS:", params)

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    print("STATUS:", response.status_code)
    print("CONTENT TYPE:", response.headers.get("content-type"))
    print("RESPONSE PREVIEW:", response.text[:1000])

    response.raise_for_status()

    return response.json()


def get_items(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in [
        "results",
        "items",
        "data",
        "standings",
        "matches",
        "registrations",
    ]:
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def get_rounds(event):
    rounds = []

    if not isinstance(event, dict):
        return rounds

    # Possible API structure #1
    for phase in event.get("tournament_phases", []) or []:
        if not isinstance(phase, dict):
            continue

        for rnd in phase.get("rounds", []) or []:
            if isinstance(rnd, dict):
                rounds.append(rnd)

    # Possible API structure #2
    if not rounds:
        for rnd in event.get("rounds", []) or []:
            if isinstance(rnd, dict):
                rounds.append(rnd)

    return rounds


def round_number(rnd):
    for key in [
        "round_number",
        "roundNumber",
        "number",
        "sequence",
    ]:
        value = rnd.get(key)

        if value is not None:
            try:
                return int(value)
            except Exception:
                pass

    return 0


def get_round_standings(round_id):
    paths = [
        f"/tournament-rounds/{round_id}/standings/paginated/",
        f"/tournament-rounds/{round_id}/standings/",
    ]

    for path in paths:
        try:
            data = api_get(
                path,
                {
                    "page": 1,
                    "page_size": 500,
                },
            )

            items = get_items(data)

            print(
                f"STANDINGS: round={round_id}, "
                f"path={path}, "
                f"items={len(items)}"
            )

            if items:
                return items

        except Exception as exc:
            print("STANDINGS ERROR:", repr(exc))

    return []


def get_round_matches(round_id):
    paths = [
        f"/tournament-rounds/{round_id}/matches/paginated/",
        f"/tournament-rounds/{round_id}/matches/",
    ]

    for path in paths:
        try:
            data = api_get(
                path,
                {
                    "page": 1,
                    "page_size": 500,
                },
            )

            items = get_items(data)

            print(
                f"MATCHES: round={round_id}, "
                f"path={path}, "
                f"items={len(items)}"
            )

            if items:
                return items

        except Exception as exc:
            print("MATCHES ERROR:", repr(exc))

    return []


def get_fresh_data():

    print("=" * 80)
    print("STARTING RAVENSBURGER IMPORT")
    print("EVENT:", EVENT_ID)
    print("=" * 80)

    event = api_get(
        f"/events/{EVENT_ID}/"
    )

    print("=" * 80)
    print("EVENT RESPONSE TYPE:", type(event).__name__)

    if isinstance(event, dict):
        print("EVENT KEYS:")
        print(list(event.keys()))

    print("=" * 80)

    rounds = get_rounds(event)

    print("ROUNDS FOUND:", len(rounds))

    for rnd in rounds:
        print(
            "ROUND:",
            json.dumps(rnd, ensure_ascii=False)[:2000]
        )

    all_rounds = []

    for rnd in rounds:

        round_id = rnd.get("id")

        if not round_id:
            print("ROUND WITHOUT ID:", rnd)
            continue

        round_no = round_number(rnd)

        standings = get_round_standings(round_id)
        matches = get_round_matches(round_id)

        all_rounds.append(
            {
                "id": round_id,
                "round": round_no,
                "standings": standings,
                "matches": matches,
            }
        )

    print("=" * 80)
    print("IMPORT SUMMARY")
    print("Rounds:", len(all_rounds))

    for rnd in all_rounds:
        print(
            f"Round {rnd['round']} "
            f"(ID {rnd['id']}): "
            f"{len(rnd['standings'])} standings, "
            f"{len(rnd['matches'])} matches"
        )

    print("=" * 80)

    # Keep the existing tracked players.
    tracked = []

    if DATA_FILE.exists():
        try:
            old = json.loads(
                DATA_FILE.read_text(
                    encoding="utf-8"
                )
            )

            tracked = old.get("players", [])

        except Exception as exc:
            print("Could not read old event.json:", exc)

    # Find latest round with standings.
    latest = None

    for rnd in reversed(all_rounds):
        if rnd["standings"]:
            latest = rnd
            break

    participant_count = 0

    if latest:
        participant_count = len(
            latest["standings"]
        )

    result = {
        "event": {
            "id": EVENT_ID,
            "name": event.get(
                "name",
                "Iconic Tour - CCQ"
            ) if isinstance(event, dict) else "Iconic Tour - CCQ",
            "players": participant_count,
            "current_round": (
                latest["round"]
                if latest
                else None
            ),
        },

        "last_updated": datetime.now(
            timezone.utc
        ).isoformat(),

        "players": tracked,

        "standings": (
            latest["standings"]
            if latest
            else []
        ),

        "rounds": all_rounds,
    }

    print(
        "FINAL:",
        len(result["standings"]),
        "standings /",
        len(result["rounds"]),
        "rounds"
    )

    return result
