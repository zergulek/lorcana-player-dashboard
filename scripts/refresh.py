from pathlib import Path
from datetime import datetime, timezone
import json


BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "event.json"


def get_fresh_data():

    data = json.loads(
        DATA.read_text(
            encoding="utf-8"
        )
    )

    data["last_updated"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    return data


def main():

    data = get_fresh_data()

    DATA.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "Updated",
        DATA,
    )


if __name__ == "__main__":
    main()from pathlib import Path
from datetime import datetime, timezone
import json

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "event.json"

# IMPORTANT:
# Replace this function with the normalized output from your existing
# lorcana_ravensburger_scraper project.
def get_fresh_data():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    return data

def main():
    data = get_fresh_data()
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Updated", DATA)

if __name__ == "__main__":
    main()
