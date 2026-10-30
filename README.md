# HPL Watcher frontend

Independent, on-demand Hamilton Public Library Rec Pass Express lookup for Hamilton Conservation Authority and Royal Ontario Museum passes. Checks HPL directly when the page opens or **Check availability** is pressed. No scheduled tracker, snapshot file, email credentials or notification baseline is required.

## Update and run on Windows

Stop the frontend with Ctrl+C, then:

```powershell
cd C:\Dev\hpl-tracker-front
git pull
python -m pip install -r requirements.txt
python -m playwright install chromium
python server.py
```

Open http://127.0.0.1:31008. Leave the existing scheduled email tracker running independently. No need to copy files into its folder or set `HPL_DATA_DIR` for this frontend. Earlier `watcher.py` and `snapshot.py` files remain for compatibility but the server never imports or runs them.

## How checks work

A single background check loads the HPL availability-by-location overlay for both titles using Playwright. Only the exact Rec Pass Express collection is included. Actual available holding rows are counted per branch. Missing sections and partially parsed Express rows fail rather than being published as zero.

The page polls progress while the server checks. Concurrent visitors share the in-flight check, and completed checks have a 30-second shared cache, including failed checks. Requests within that window reuse the result and retain its actual check time. Opening another tab or repeatedly clicking does not launch more browsers. Checks may take a minute or two; nothing blocks the web server's normal responses.

Results are kept in memory, independently of the tracker. A restart clears them. A failed check keeps previous results but flags them unconfirmed and excludes them from Available now. Results older than 11 minutes are also excluded until checked again. No automatic scheduled scraping runs in this frontend.

## Startup task

For unattended use run `scripts\setup.ps1` from Administrator PowerShell with a machine-wide Python installation. Install the browser for the task account as well: Playwright's default browser directory belongs to the installing user. A shared browser installation can be configured before setup:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = 'C:\ProgramData\HPLFrontend\browsers'
[Environment]::SetEnvironmentVariable('PLAYWRIGHT_BROWSERS_PATH', $env:PLAYWRIGHT_BROWSERS_PATH, 'Machine')
python -m playwright install chromium
.\scripts\setup.ps1
```

Dependencies must be installed in the same Python used by the task. The task uses startup, restart on failure, localhost port 31008 and no execution time limit. The runner explicitly reloads the machine browser path. Existing watcher tasks and state are untouched.

## Caddy

```caddyfile
hpl.pelaxix.com {
    reverse_proxy 127.0.0.1:31008
}
```

Point DNS at the same home-server target as the other pelaxix.com apps, validate and reload Caddy. These host changes are not performed by this repository.

## API and checks

- `POST /api/check`: start or join a check, or use a result younger than 30 seconds.
- `GET /api/status`: read results and progress without launching a check.
- `GET /api/health`: frontend process health, independent of HPL availability.

```powershell
python -m unittest discover -s tests -v
```

Parser tests use fixtures shaped like the supplied watcher's catalogue output. Service tests use injected runners and never send email or access HPL. Live HPL checks must be verified on the deployment host.

Design: TasteSkill Framed Sheet, seed 49437092. Light/dark modes, branch search, available-only filter, Google Maps directions and catalogue links.
