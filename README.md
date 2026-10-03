# Lorcana Player Dashboard

Public dashboard for selected players in Ravensburger Play Network event 1007231.

## What is included

- FastAPI web dashboard
- Responsive player list
- Search and player selection
- Per-player match history
- JSON API
- Health endpoint
- Render Blueprint with a web service + 5-minute cron refresh
- Normalized data format for plugging in your existing Ravensburger scraper

## Deploy on Render

1. Create a GitHub repository.
2. Upload the contents of this folder to the repository.
3. In Render, choose **New > Blueprint** and select the repository.
4. Render reads `render.yaml` and creates the web service and refresh cron job.
5. Open the URL Render gives the web service.

Render cron schedules use UTC. The included schedule runs every 5 minutes. See Render's cron documentation:
https://render.com/docs/cronjobs

## Important

The scraper adapter in `scripts/refresh.py` intentionally does not guess undocumented Ravensburger API endpoints. Plug your existing scraper into `scripts/source_adapter.py`, or copy its generated normalized JSON into `data/event.json`.

The dashboard is already usable with the sample structure in `data/event.json`.

## Data format

`data/event.json`:

{
  "event": {...},
  "last_updated": "...",
  "players": [
    {
      "name": "...",
      "tag": "...",
      "rank": 1,
      "points": 9,
      "match_wins": 3,
      "match_losses": 0,
      "game_wins": 6,
      "game_losses": 1,
      "opponent": "...",
      "status": "active",
      "matches": [
        {"round": 1, "opponent": "...", "result": "W", "score": "2-0", "table": 12}
      ]
    }
  ]
}
