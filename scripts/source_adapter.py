import os
import requests


API_BASE = "https://api.cloudflare.ravensburgerplay.com/hydraproxy/api/v2"
EVENT_ID = os.getenv("EVENT_ID", "1007231")


def get_fresh_data():

    url = f"{API_BASE}/events/{EVENT_ID}/"

    response = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "Referer": "https://tcg.ravensburgerplay.com/",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=30,
    )

    response.raise_for_status()

    event = response.json()

    print("Ravensburger event loaded")
    print("Event ID:", event.get("id"))
    print("Event name:", event.get("name"))

    return {
        "event": {
            "id": str(event.get("id", EVENT_ID)),
            "name": event.get(
                "name",
                "Iconic Tour - CCQ",
            ),
            "format": event.get(
                "format",
                "Core Constructed",
            ),
            "players": 0,
        },

        "last_updated": None,

        "players": [],
    }
