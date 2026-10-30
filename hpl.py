"""Direct HPL lookups only: no notification state or email dependencies."""
import re
from collections import Counter
from playwright.sync_api import sync_playwright

TARGET_COLLECTION = "Rec Pass Express"

def log(message):
    print(message, flush=True)

def normalize_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]

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

    # Every Express row in the available section must have parsed successfully.
    express_rows = sum(line.casefold() == TARGET_COLLECTION.casefold()
                       for line in normalize_lines(available_text))
    if sum(branches.values()) != express_rows:
        raise RuntimeError("Some available Express holdings could not be parsed")
    if int(re.search(r"\d+", available_match.group()).group()) > 0 and not normalize_lines(available_text):
        raise RuntimeError("Available holdings have not populated")
    return [{"name": name, "available": count} for name, count in sorted(branches.items())]

def check_passes(definitions, publish):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="en-CA")
            page = context.new_page()
            for definition in definitions:
                item = {"id": definition["id"], "short_name": definition["shortName"], "url": definition["catalogueUrl"]}
                try:
                    branches = scrape_express_available(page, item)
                    publish(item["id"], branches, None)
                except Exception as exc:
                    log(f"HPL lookup failed for {item['id']}: {type(exc).__name__}: {exc}")
                    publish(item["id"], None, "Could not check HPL. Try again or use the catalogue.")
        finally:
            browser.close()
