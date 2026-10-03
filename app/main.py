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
    version="2.0.0",
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC),
    name="static",
)


CACHE_SECONDS = 60

_cache = None
_cache_time = 0.0
_cache_lock = threading.Lock()


def load_data():
    global _cache
    global _cache_time

    now = time.time()

    if _cache is not None and now - _cache_time < CACHE_SECONDS:
        return _cache

    with _cache_lock:
        now = time.time()

        if _cache is not None and now - _cache_time < CACHE_SECONDS:
            return _cache

        try:
            _cache = get_fresh_data()
            _cache_time = now

            print(
                "Ravensburger data refreshed successfully: "
                f"{len(_cache.get('players', []))} tracked players"
            )

            return _cache

        except Exception as exc:
            print(
                "ERROR: Could not refresh Ravensburger data:",
                repr(exc),
            )

            if _cache is not None:
                # Keep serving the last known good data.
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
                "error": str(exc),
            }


@app.get("/", response_class=HTMLResponse)
def index():
    return (
        STATIC / "index.html"
    ).read_text(encoding="utf-8")


@app.get("/api/event")
def event():
    return JSONResponse(load_data())


@app.get("/api/health")
def health():
    data = load_data()

    return {
        "ok": "error" not in data,
        "event_id": data.get("event", {}).get("id"),
        "players": data.get("event", {}).get("players", 0),
        "tracked": len(data.get("players", [])),
        "last_updated": data.get("last_updated"),
        "error": data.get("error"),
    }


@app.get("/api/players")
def players():
    return {
        "players": load_data().get("players", [])
    }
