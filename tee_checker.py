#!/usr/bin/env python3
"""
Francis A. Byrne tee time watcher.

Checks the Essex County ForeUP tee sheet for Saturday/Sunday tee times between
8:00 AM and 2:00 PM with room for 4 golfers, and sends a push notification
through ntfy when a new one appears.

Usage:
  python tee_checker.py               normal check (what the schedule runs)
  python tee_checker.py --test        send a test push to your phone
  python tee_checker.py --discover    list the booking classes the course offers
  python tee_checker.py --dry-run     check and print, but don't notify or save
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# ---- Settings you might want to change -------------------------------------
PLAYERS = 4
EARLIEST = dtime(8, 0)    # earliest tee time you want
LATEST = dtime(14, 0)     # latest tee time you want
WEEKEND_DAYS = {5, 6}     # Monday=0 ... Saturday=5, Sunday=6
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "14"))
# ----------------------------------------------------------------------------

COURSE_ID = "22527"
SCHEDULE_ID = "11077"
TZ = ZoneInfo("America/New_York")
BOOKING_PAGE = f"https://foreupsoftware.com/index.php/booking/{COURSE_ID}/{SCHEDULE_ID}"
BOOKING_LINK = BOOKING_PAGE + "#teetimes"
API_URL = "https://foreupsoftware.com/index.php/api/booking/times"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Api-Key": "no_limits",
    "Referer": BOOKING_PAGE,
}

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
BOOKING_CLASS = os.getenv("BOOKING_CLASS", "").strip()
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))
FAIL_ALERT_AFTER = 6  # consecutive failed runs (~1 hour) before warning you


# ---- Notifications ---------------------------------------------------------
def notify(title, body, priority="high", tags="golf"):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set, would have sent:\n", title, "\n", body)
        return
    r = requests.post(
        f"{NTFY_SERVER}/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Tags": tags, "Click": BOOKING_LINK},
        timeout=15,
    )
    r.raise_for_status()


# ---- State (remembers what you've already been told about) -----------------
def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


# ---- ForeUP ----------------------------------------------------------------
def discover_booking_classes():
    """Scrape the public booking page for booking class ids and names."""
    html = requests.get(BOOKING_PAGE, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=20).text
    found = {}
    for m in re.finditer(r'"booking_class_id"\s*:\s*"?(\d+)"?\s*,\s*"name"\s*:\s*"([^"]+)"', html):
        found[m.group(1)] = m.group(2)
    for m in re.finditer(r'"name"\s*:\s*"([^"]+)"[^{}]{0,200}?"booking_class_id"\s*:\s*"?(\d+)"?', html):
        found.setdefault(m.group(2), m.group(1))
    return found


def pick_booking_class():
    classes = discover_booking_classes()
    if not classes:
        return ""
    for cid, name in classes.items():
        if re.search(r"public|non.?res|guest|general", name, re.I):
            print(f"Using booking class {cid} ({name})")
            return cid
    cid = next(iter(classes))
    print(f"Using first booking class found: {cid} ({classes[cid]})")
    return cid


def fetch_times(day, booking_class):
    params = {
        "time": "all",
        "date": day.strftime("%m-%d-%Y"),
        "holes": "all",
        "players": PLAYERS,
        "schedule_id": SCHEDULE_ID,
        "schedule_ids[]": SCHEDULE_ID,
        "specials_only": "0",
        "api_key": "no_limits",
    }
    if booking_class:
        params["booking_class"] = booking_class
    r = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        return None


def upcoming_weekend_days(now):
    today = now.date()
    return [today + timedelta(days=i) for i in range(DAYS_AHEAD + 1)
            if (today + timedelta(days=i)).weekday() in WEEKEND_DAYS]


def matching_slots(raw, now):
    """Filter one day's API response down to slots you'd actually take."""
    slots = {}
    for item in raw or []:
        try:
            t = datetime.strptime(item["time"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        except (KeyError, ValueError, TypeError):
            continue
        spots = int(item.get("available_spots") or 0)
        holes = str(item.get("holes", ""))
        if t <= now or not (EARLIEST <= t.time() <= LATEST):
            continue
        if t.weekday() not in WEEKEND_DAYS or spots < PLAYERS or holes == "9":
            continue
        slots[t.strftime("%Y-%m-%d %H:%M")] = {"spots": spots, "holes": holes or "?"}
    return slots


def describe(key, info):
    t = datetime.strptime(key, "%Y-%m-%d %H:%M")
    label = t.strftime("%a %b %-d, %-I:%M %p")
    return f"{label}  ({info['holes']} holes, {info['spots']} spots)"


# ---- Main ------------------------------------------------------------------
def run(dry_run=False):
    state = load_state()
    now = datetime.now(TZ)
    booking_class = BOOKING_CLASS

    days = upcoming_weekend_days(now)
    current, got_list, errors = {}, False, []

    for attempt in range(2):
        current, got_list, errors = {}, False, []
        for day in days:
            try:
                raw = fetch_times(day, booking_class)
            except requests.RequestException as e:
                errors.append(f"{day}: {e}")
                continue
            if isinstance(raw, list):
                got_list = True
                current.update(matching_slots(raw, now))
            else:
                print(f"{day}: non-list response: {str(raw)[:200]}")
        if got_list or booking_class or attempt == 1:
            break
        # No usable response without a booking class; try to find one.
        booking_class = pick_booking_class()
        if not booking_class:
            break

    if errors:
        print("Errors:\n  " + "\n  ".join(errors))

    if not got_list:
        state["failures"] = state.get("failures", 0) + 1
        print(f"Could not read the tee sheet (failure #{state['failures']}).")
        if state["failures"] >= FAIL_ALERT_AFTER and not state.get("fail_alerted") and not dry_run:
            notify("Tee watcher needs attention",
                   "The Byrne tee time checker hasn't been able to read the tee sheet "
                   "for about an hour. Open the GitHub Actions log to see why.",
                   priority="default", tags="warning")
            state["fail_alerted"] = True
        if not dry_run:
            save_state(state)
        return 1

    state["failures"], state["fail_alerted"] = 0, False
    previous = set(state.get("available", []))
    new_keys = sorted(k for k in current if k not in previous)

    print(f"Checked {len(days)} weekend days. Matching slots now: {len(current)}. New: {len(new_keys)}.")
    for k in sorted(current):
        print("  " + describe(k, current[k]) + ("  NEW" if k in new_keys else ""))

    if new_keys and not dry_run:
        lines = [describe(k, current[k]) for k in new_keys[:10]]
        if len(new_keys) > 10:
            lines.append(f"...and {len(new_keys) - 10} more")
        title = "Byrne tee time open!" if len(new_keys) == 1 else f"{len(new_keys)} Byrne tee times open!"
        notify(title, "\n".join(lines) + "\n\nTap to book.")

    if not dry_run:
        state["available"] = sorted(current)
        save_state(state)
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--test":
        notify("Tee watcher test", "If you see this, alerts are working. Tap to open the tee sheet.",
               priority="default", tags="white_check_mark")
        print("Test notification sent.")
    elif arg == "--discover":
        classes = discover_booking_classes()
        print("Booking classes found:" if classes else "No booking classes found on the page.")
        for cid, name in classes.items():
            print(f"  {cid}: {name}")
    else:
        sys.exit(run(dry_run=(arg == "--dry-run")))
