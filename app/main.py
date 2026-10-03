from pathlib import Path
from datetime import datetime, timezone
import json
import time

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scripts.source_adapter import get_fresh_data


BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "event.json"
STATIC = BASE / "app" / "static"

app = FastAPI(
    title="Lorcana Player Dashboard",
    version="1.0.0",
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC),
    name="static",
)


# ---------------------------------------------------------
# CACHE
# ---------------------------------------------------------

CACHE_TTL = 60

_cache = {
    "data": None,
    "timestamp": 0,
}


# ---------------------------------------------------------
# STATIC FALLBACK
# ---------------------------------------------------------

def load_static_data():
    """Load the old static data as a fallback."""

    try:
        return json.loads(
            DATA.read_text(encoding="utf-8")
        )

    except Exception as exc:
        return {
            "event": {
                "id": "1007231",
                "name": "Iconic Tour - CCQ",
                "players": 0,
            },
            "last_updated": None,
            "players": [],
            "error": str(exc),
        }


# ---------------------------------------------------------
# FRESH DATA
# ---------------------------------------------------------

def load_data():
    """
    Return fresh Ravensburger data.

    Data is cached for CACHE_TTL seconds.
    If the live API fails, return the previous cached data.
    If there is no previous cache, fall back to event.json.
    """

    now = time.time()

    # Use cache if it is still valid.
    if (
        _cache["data"] is not None
        and now - _cache["timestamp"] < CACHE_TTL
    ):
        return _cache["data"]

    try:
        print("========================================")
        print("Loading fresh Ravensburger data...")
        print("========================================")

        data = get_fresh_data()

        if not isinstance(data, dict):
            raise ValueError(
                f"get_fresh_data() returned "
                f"{type(data).__name__}, expected dict"
            )

        # Make sure timestamp exists.
        if not data.get("last_updated"):
            data["last_updated"] = (
                datetime.now(timezone.utc).isoformat()
            )

        # Save fresh result.
        _cache["data"] = data
        _cache["timestamp"] = now

        print(
            "Fresh data loaded successfully."
        )

        print(
            f"Players: "
            f"{len(data.get('players', []))}"
        )

        print(
            f"Event: "
            f"{data.get('event', {}).get('name')}"
        )

        print(
            f"Last updated: "
            f"{data.get('last_updated')}"
        )

        print("========================================")

        return data

    except Exception as exc:

        print("========================================")
        print("ERROR loading fresh data")
        print(str(exc))
        print("========================================")

        # If we have previous live data, keep using it.
        if _cache["data"] is not None:

            cached = dict(_cache["data"])

            cached["error"] = str(exc)

            return cached

        # Otherwise use static fallback.
        fallback = load_static_data()

        fallback["error"] = (
            f"Live data unavailable: {exc}"
        )

        return fallback


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    return (
        STATIC / "index.html"
    ).read_text(encoding="utf-8")


@app.get("/api/event")
def event():
    data = load_data()

    return JSONResponse(data)


@app.get("/api/players")
def players():
    data = load_data()

    return {
        "players": data.get("players", [])
    }


@app.get("/api/health")
def health():

    data = load_data()

    event_data = data.get("event", {})

    players_data = data.get("players", [])

    # Diagnostics
    standings_count = data.get(
        "standings_count",
        data.get("standings", 0),
    )

    current_round = event_data.get(
        "current_round"
    )

    return {
        "ok": "error" not in data,
        "event_id": event_data.get("id"),
        "event_name": event_data.get("name"),
        "participants": event_data.get("players"),
        "tracked": len(players_data),
        "standings": standings_count,
        "current_round": current_round,
        "last_updated": data.get("last_updated"),
        "error": data.get("error"),
    }
