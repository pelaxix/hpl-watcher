import argparse
import html
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
LOG_FILE = BASE_DIR / "watcher.log"

PASSES = [
    {
        "id": "hca",
        "name": "Hamilton Conservation Authority Pass",
        "short_name": "HCA Pass",
        "url": "https://hpl.bibliocommons.com/v2/record/S125C722592",
        "emoji": "🌲",
    },
    {
        "id": "rom",
        "name": "Royal Ontario Museum Pass",
        "short_name": "ROM Pass",
        "url": "https://hpl.bibliocommons.com/v2/record/S125C878844",
        "emoji": "🏛️",
    },
]

TARGET_COLLECTION = "Rec Pass Express"


def publish_snapshot(item, branches=None, error=None):
    # Frontend publication must never prevent the existing alerts from running.
    try:
        from snapshot import record_result
        record_result(item["id"], branches=branches, error=error)
    except Exception as exc:
        log(f"WARNING: Frontend snapshot not updated: {type(exc).__name__}: {exc}")


def log(message: str):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {message}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"WARNING: Could not read state.json ({exc}); treating as first run.")
        return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def normalize_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_branch_from_row(text):
    """
    BiblioCommons currently renders holdings as a row with roughly:
      Available
      Barton
      Rec Pass Express
      E PASS ...
    We deliberately require BOTH 'Available' and the exact Express collection.
    """
    lines = normalize_lines(text)
    lowered = [x.casefold() for x in lines]

    try:
        collection_index = lowered.index(TARGET_COLLECTION.casefold())
    except ValueError:
        return None

    available_indexes = [
        i for i, value in enumerate(lowered)
        if value == "available" or value.startswith("available ")
    ]
    if not available_indexes:
        return None

    # Prefer text between "Available" and "Rec Pass Express" as the location.
    before_collection = lines[:collection_index]
    available_index = available_indexes[0]

    candidates = before_collection[available_index + 1:]
    skip = {
        "availability", "location", "collection", "call number",
        "status", "available", "unavailable", "checked out",
    }
    candidates = [
        c for c in candidates
        if c.casefold() not in skip
        and TARGET_COLLECTION.casefold() not in c.casefold()
    ]

    if candidates:
        return candidates[0]

    # Fallback: last useful value before collection, excluding status/header words.
    fallback = [
        c for c in before_collection
        if c.casefold() not in skip
    ]
    return fallback[-1] if fallback else None


def scrape_express_available(page, item):
    log(f"Checking {item['short_name']}...")
    page.goto(item["url"], wait_until="domcontentloaded", timeout=60000)

    # BiblioCommons does NOT load the copy-level holdings table on the record page.
    # Open the "Availability by location" modal first; the Express rows live there.
    availability_link = page.get_by_text("Availability by location", exact=False)
    availability_link.first.wait_for(state="visible", timeout=30000)
    availability_link.first.click()

    # Wait for the modal and its holdings rows to populate.
    page.get_by_text("Availability details", exact=False).first.wait_for(
        state="visible", timeout=20000
    )
    page.wait_for_timeout(1000)

    # Wait briefly for Express rows if any exist.
    try:
        page.get_by_text(TARGET_COLLECTION, exact=True).first.wait_for(timeout=12000)
    except Exception:
        pass

    # BiblioCommons renders the holdings overlay as readable text.
    # Parsing the overlay text is more reliable than trying to infer React/table DOM structure.
    body_text = page.locator("body").inner_text(timeout=10000)

    # Isolate the currently-open availability overlay. The record page itself also contains
    # the word "Available", so start at the overlay heading.
    overlay_pos = body_text.rfind("Availability details")
    if overlay_pos >= 0:
        overlay_text = body_text[overlay_pos:]
    else:
        raise RuntimeError("Availability overlay heading was not found")

    # Only inspect the "Available (...)" section. Anything below
    # "Not available at this time" is irrelevant to alerts.
    available_match = re.search(r"Available\s*\(\d+\)", overlay_text, flags=re.IGNORECASE)
    if available_match:
        available_text = overlay_text[available_match.end():]
    else:
        raise RuntimeError("Available holdings section was not found; refusing to publish an empty result")

    unavailable_marker = re.search(
        r"Not available at this time\s*\(\d+\)",
        available_text,
        flags=re.IGNORECASE,
    )
    if unavailable_marker:
        available_text = available_text[:unavailable_marker.start()]

    # Parse each available holding from the overlay text.
    # BiblioCommons currently emits rows like:
    #
    #   Barton\t
    #   Rec Pass Express
    #   \tPASS ROM\tAvailable
    #
    # so Call No. and Status can be on the SAME line, separated by tabs.
    branches = Counter()

    pattern = re.compile(
        r"(?:^|\n)"
        r"\s*([^\n\t]+?)\s*\t?\s*\n"
        r"\s*Rec Pass Express\s*\n"
        r"\s*\t?[^\n\t]+\t+Available\s*(?=\n|$)",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(available_text):
        branch = match.group(1).strip()
        if branch.casefold() not in {
            "location", "collection", "call no.", "call no", "status", "available"
        }:
            branches[branch] += 1

    # Keep a debug dump only when parsing finds nothing, so future page changes are easy to inspect.
    if not branches:
        debug = BASE_DIR / f"debug-{item['id']}.txt"
        debug.write_text(body_text, encoding="utf-8")
        log(
            f"No available Express branches parsed for {item['short_name']}; "
            f"debug text saved to {debug.name}"
        )

    # Every Express row in the available section must have parsed successfully.
    express_rows = sum(line.casefold() == TARGET_COLLECTION.casefold()
                       for line in normalize_lines(available_text))
    if sum(branches.values()) != express_rows:
        raise RuntimeError("Some available Express holdings could not be parsed")
    if int(re.search(r"\d+", available_match.group()).group()) > 0 and not normalize_lines(available_text):
        raise RuntimeError("Available holdings have not populated")
    return [{"name": name, "available": count} for name, count in sorted(branches.items())]


def maps_url(branch):
    destination = f"Hamilton Public Library {branch} Branch, Ontario"
    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(destination)}"


def email_html(item, branch):
    branch_safe = html.escape(branch)
    title_safe = html.escape(item["short_name"])
    directions = maps_url(branch)

    # Email-safe table layout, intentionally simple for iPhone Mail/Gmail.
    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f3f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f6f8;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="max-width:520px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #dbe3e8;">
        <tr>
          <td style="background:#0072bc;padding:22px 24px;color:#ffffff;">
            <div style="font-size:12px;font-weight:700;letter-spacing:1.4px;opacity:.9;">HAMILTON PUBLIC LIBRARY</div>
            <div style="font-size:28px;font-weight:800;margin-top:6px;">{item['emoji']} {title_safe}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:26px 24px;">
            <div style="display:inline-block;background:#e7f6ec;color:#17743a;border-radius:999px;
                        padding:7px 11px;font-size:13px;font-weight:800;letter-spacing:.4px;">
              AVAILABLE NOW
            </div>
            <div style="font-size:25px;font-weight:800;color:#18242c;margin-top:18px;">{branch_safe} Branch</div>
            <div style="font-size:15px;line-height:1.5;color:#59666f;margin-top:8px;">
              An Express pass just became available. Express passes can't be held, so this is your cue to move.
            </div>
            <table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:24px;">
              <tr>
                <td bgcolor="#0072bc" style="border-radius:10px;">
                  <a href="{directions}"
                     style="display:inline-block;padding:14px 20px;color:#ffffff;text-decoration:none;
                            font-size:16px;font-weight:800;">
                    📍 GET DIRECTIONS
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:15px 24px;background:#eef5f8;color:#66757e;font-size:12px;">
            HPL Pass Watcher • detected {datetime.now().strftime("%-I:%M %p") if os.name != "nt" else datetime.now().strftime("%I:%M %p").lstrip("0")}
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email(item, branch):
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "BREVO_API_KEY is not available in the Windows environment for this process."
        )

    sender_email = "notificaciones@grupofginmobiliario.com"
    recipient_email = "pelaxix@gmail.com"
    subject = f"🚨 {item['short_name']} Available — {branch} Branch"

    payload = {
        "sender": {
            "name": "HPL Pass Watcher",
            "email": sender_email,
        },
        "to": [
            {
                "email": recipient_email,
                "name": "Fernando",
            }
        ],
        "subject": subject,
        "htmlContent": email_html(item, branch),
        "textContent": (
            f"{item['short_name']} is available at {branch} Branch.\n\n"
            f"Directions: {maps_url(branch)}"
        ),
    }

    data = json.dumps(payload).encode("utf-8")
    request = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=data,
        method="POST",
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Brevo returned HTTP {response.status}: {body}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Brevo returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Brevo: {exc}") from exc

    log(f"EMAIL SENT via Brevo: {item['short_name']} → {branch} Branch")


def send_test_email():
    item = PASSES[1]
    send_email(item, "Barton")
    print("\nTest email sent. It intentionally uses a fake 'ROM at Barton' alert so you can preview the design.")


def run_check(notify=True):
    state = load_state()
    first_run = not bool(state)
    new_state = dict(state)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1000},
            locale="en-CA",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/129.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for item in PASSES:
            try:
                try:
                    holdings = scrape_express_available(page, item)
                except Exception:
                    publish_snapshot(item, error="Catalogue check failed; previous results retained")
                    raise
                publish_snapshot(item, branches=holdings)
                current = [branch["name"] for branch in holdings]
                previous = state.get(item["id"], {}).get("available_branches", [])
                newly_available = sorted(set(current) - set(previous))

                log(
                    f"{item['short_name']}: Express available now = "
                    f"{', '.join(current) if current else 'none'}"
                )

                # FIRST RUN = baseline only, no surprise spam for things already available.
                if not first_run and notify:
                    for branch in newly_available:
                        send_email(item, branch)

                new_state[item["id"]] = {
                    "available_branches": current,
                    "last_successful_check": datetime.now().isoformat(timespec="seconds"),
                }
            except Exception as exc:
                log(f"ERROR checking {item['short_name']}: {type(exc).__name__}: {exc}")
                # Preserve previous state for this pass on failure.

        browser.close()

    save_state(new_state)

    if first_run:
        log("Baseline created. No notifications sent on first run.")


def main():
    parser = argparse.ArgumentParser(description="Watch HPL Express recreation passes.")
    parser.add_argument("--test-email", action="store_true", help="Send a styled test email.")
    parser.add_argument("--reset-baseline", action="store_true", help="Delete state and rebuild baseline.")
    args = parser.parse_args()

    if args.test_email:
        send_test_email()
        return

    if args.reset_baseline and STATE_FILE.exists():
        STATE_FILE.unlink()
        log("Baseline deleted.")

    run_check(notify=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"FATAL: {type(exc).__name__}: {exc}")
        sys.exit(1)
