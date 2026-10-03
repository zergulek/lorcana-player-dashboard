from pathlib import Path
import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


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


def load_data():
    try:
        return json.loads(
            DATA.read_text(
                encoding="utf-8"
            )
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


@app.get("/api/health")
def health():
    data = load_data()

    return {
        "ok": "error" not in data,
        "event_id": data.get(
            "event",
            {},
        ).get("id"),
    }


@app.get("/api/players")
def players():
    return {
        "players": load_data().get(
            "players",
            [],
        )
    }
