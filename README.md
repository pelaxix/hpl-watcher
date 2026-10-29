# HPL Watcher

A quick, mobile-friendly view of Hamilton Public Library **Rec Pass Express** availability for Hamilton Conservation Authority and Royal Ontario Museum passes. TasteSkill Framed Sheet, light/dark themes, branch search, available-only filter, catalogue links, Google Maps directions, and per-pass freshness.

## Run

Requires Python 3.10+. The frontend has no third-party Python dependencies.

```powershell
git clone https://github.com/pelaxix/hpl-watcher.git C:\Dev\hpl-watcher
cd C:\Dev\hpl-watcher
python server.py
```

Open http://127.0.0.1:31008. Before the first watcher publication the page says “Awaiting first check”; it never supplies demonstration availability. Refresh results reads saved watcher output; it does not scrape HPL or trigger email notifications. The page refreshes results every minute.

## Connect the existing scheduled watcher

The original watcher script has not yet been supplied to this repository. Keep that job and its existing unavailable→available email logic, five-minute schedule, first-scan baseline and saved state. This repo does **not** install a replacement scraper or modify email delivery.

Copy `snapshot.py` beside the existing `watcher.py`, then import it:

```python
from snapshot import record_result
```

After a **complete successful** scan of each title, pass only the `Rec Pass Express` branches and their actual available-copy counts:

```python
# Variables below must come from the existing scraper, not the title-level total.
record_result("hca", hca_express_branches)
record_result("rom", rom_express_branches)
# Each is a list of {"name": branch_name, "available": available_count}.
# A verified successful scan with none available is [].
```

Call sequentially from one watcher job. The snapshot helper atomically replaces `availability.json`, preserving the other title. Do not run concurrent publishers. If an empty result means the scrape failed or a selector changed, publish an error instead of an empty successful scan:

```python
record_result("rom", error="Catalogue check failed")
```

Errors preserve the last successful results and timestamp. The UI marks them as previous results, excludes them from Available now, and links to the catalogue. Results older than 11 minutes are also stale. Both watcher and frontend must use the **same** `HPL_DATA_DIR` (recommended `D:\DevData\HPLWatcher`). This snapshot is separate from the watcher's notification baseline.

A CLI is also available for non-Python watchers: `python snapshot.py rom --branches-json <JSON-array>` or `python snapshot.py rom --error "Catalogue check failed"`. Never publish a success until the availability-by-location table was parsed completely and filtered to Rec Pass Express.

## Windows startup and Caddy

From an Administrator PowerShell, with a machine-wide Python installation available to SYSTEM:

```powershell
.\scripts\setup.ps1
```

This registers `HPL-Watcher-Frontend` at startup with automatic restart on failure and no execution time limit. It uses port 31008, binds only to localhost, and sets machine environment variables. Restart the existing watcher task after setting its snapshot import/data path so it picks up the environment. If Python is installed only for your user, use a machine-wide installation before running the setup script.

Add to the existing Caddyfile:

```caddyfile
hpl.pelaxix.com {
    reverse_proxy 127.0.0.1:31008
}
```

Create the DNS record using the same home-server target as the other pelaxix.com apps, validate the Caddy configuration, then reload Caddy. This repository does not change DNS or the running Caddy configuration automatically.

```powershell
curl.exe http://127.0.0.1:31008/api/health
curl.exe http://127.0.0.1:31008/api/status
```

`ok` means the frontend can read its data; `watcherFresh` is true only when both passes have recent successful checks. Data directory contents and environment secrets are not served by the web server. Public endpoints expose only availability and health; no public endpoint runs scrapers or sends emails. Keep detailed exception traces and personal information out of published errors.

## Development

```sh
python -m unittest discover -s tests -v
node --check public/app.js
```

Design: TasteSkill Framed Sheet, seed 49437092. A muted green-grey frame around a white sheet, Plex Sans, and a small open-book mark. The main question is “Which pass can I pick up, and where?” Availability belongs to pass/branch rows, with no invented metrics or charts.
