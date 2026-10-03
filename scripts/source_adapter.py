# Adapter for your existing Ravensburger scraper.
# Return data in the normalized structure described in README.md.
#
# Example:
# from pathlib import Path
# import json
#
# def load_from_existing_scraper():
#     raw = json.loads(Path("raw/event_1007231.json").read_text())
#     ...
#     return normalized
#
# Keep this module free of credentials. If the source needs authentication,
# use environment variables and document them in README.md.
