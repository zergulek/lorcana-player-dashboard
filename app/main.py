from pathlib import Path
import time
import threading

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scripts.source_adapter import get_fresh_data


BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "app" / "static"

app = FastAPI(
    title="Lorcana Player Dashboard",
    version="3.0.0",
)

app.mount(
    "/static",
    StaticFiles(
        directory=STATIC
    ),
    name="static",
)

CACHE_SECONDS = 60

_cache = None
_cache_time = 0
_lock = threading.Lock()


def load_data():

    global _cache
    global _cache_time

    now = time.time()

    if (
        _cache is not None
        and now - _cache_time < CACHE_SECONDS
    ):
        return _cache

    with _lock:

        now = time.time()

        if (
            _cache is not None
            and now - _cache_time < CACHE_SECONDS
        ):
            return _cache

        try:

            data = get_fresh_data()

            _cache = data
            _cache_time = now

            print(
                "Ravensburger data refreshed"
            )

            print(
                f"Participants: "
                f"{data['event']['players']}"
            )

            print(
                f"Tracked: "
                f"{len(data['players'])}"
            )

            return data

        except Exception as exc:

            print(
                "ERROR loading Ravensburger:",
                repr(exc),
            )

            if _cache is not None:
                return _cache

            return {
                "event": {
                    "id": "1007231",
                    "name": "Iconic Tour - CCQ",
                    "players": 0,
                    "current_round": None,
                },
                "last_updated": None,
                "players": [],
                "standings": [],
                "rounds": [],
                "error": str(exc),
            }


@app.get(
    "/",
    response_class=HTMLResponse,
)
def index():

    return (
        STATIC / "index.html"
    ).read_text(
        encoding="utf-8"
    )


@app.get("/api/event")
def event():

    return JSONResponse(
        load_data()
    )


@app.get("/api/players")
def players():

    return {
        "players": load_data().get(
            "players",
            [],
        )
    }


@app.get("/api/standings")
def standings():

    data = load_data()

    return {
        "event": data.get(
            "event",
            {},
        ),
        "standings": data.get(
            "standings",
            [],
        ),
    }


@app.get("/api/rounds")
def rounds():

    return {
        "rounds": load_data().get(
            "rounds",
            [],
        )
    }


@app.get("/api/health")
def health():

    data = load_data()

    return {
        "ok": "error" not in data,
        "event_id": data.get(
            "event",
            {},
        ).get("id"),
        "participants": data.get(
            "event",
            {},
        ).get("players", 0),
        "tracked": len(
            data.get(
                "players",
                [],
            )
        ),
        "standings": len(
            data.get(
                "standings",
                [],
            )
        ),
        "rounds": len(
            data.get(
                "rounds",
                [],
            )
        ),
        "last_updated": data.get(
            "last_updated"
        ),
        "error": data.get(
            "error"
        ),
    }
