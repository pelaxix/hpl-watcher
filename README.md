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

`watcher.py` is the existing supplied Playwright/Brevo watcher, now publishing per-branch copy counts to the frontend after each successful scrape. It preserves branch-level alerts and the existing `state.json` layout. Snapshot failures do not block alerts; scrape failures keep previous frontend results and mark them unconfirmed.

### Update an existing watcher without changing its scheduled task

After `git pull`, copy `watcher.py` and `snapshot.py` from this repo into the folder containing your existing watcher. Back up the old script first. **Keep `state.json` in its existing location** so the notification baseline is preserved. Do not reset the baseline during this update.

Both processes must use the same snapshot folder. In the PowerShell window running the frontend:

```powershell
$env:HPL_DATA_DIR = 'D:\DevData\HPLWatcher'
python server.py
```

Set the same value as a machine environment variable in an Administrator PowerShell so the scheduled watcher can use it:

```powershell
[Environment]::SetEnvironmentVariable('HPL_DATA_DIR', 'D:\DevData\HPLWatcher', 'Machine')
```

When invoking the watcher manually, also set `$env:HPL_DATA_DIR` in that window. A successful `python watcher.py` writes the snapshot as well as performing the existing alert checks. It may send an email when a branch has become available since the saved baseline. The frontend's Refresh results button only reads snapshots.

The existing watcher Python environment must still have Playwright/Chromium and its `BREVO_API_KEY`. No new watcher task is installed. If Task Scheduler retains an older environment, explicitly set `HPL_DATA_DIR` in its existing launcher before starting Python. Ensure the watcher account can write the shared folder.

The helper atomically replaces `availability.json` and preserves the other pass. Call it from only one watcher job at a time. Results older than 11 minutes and failed checks are excluded from Available now. The snapshot is separate from the notification baseline. Catalogue parsing refuses missing sections and partially parsed Express rows instead of publishing those as zero availability.

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
