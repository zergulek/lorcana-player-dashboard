from pathlib import Path
from datetime import datetime, timezone
import json
import sys


BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "event.json"

# Make the project root available for imports
sys.path.insert(0, str(BASE))

from scripts.source_adapter import get_fresh_data


def main():
    print("Starting refresh...")

    data = get_fresh_data()

    data["last_updated"] = datetime.now(
        timezone.utc
    ).isoformat()

    DATA.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("Refresh completed.")
    print("Updated:", DATA)


if __name__ == "__main__":
    main()
