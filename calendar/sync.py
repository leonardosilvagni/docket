#!/usr/bin/env python3
"""Docket calendar sync (optional): Vikunja tasks with a due date -> a CalDAV calendar.

One way and read-only on the Vikunja side: it lists tasks, and writes only to its own
calendar in Radicale. Open tasks with a due date become events; done tasks, tasks without
a due date and tasks in skipped projects (default: Inbox) are removed from the calendar.
Python standard library only.

  python -u sync.py            keep syncing every CALENDAR_SYNC_SECONDS (default 300)
  python -u sync.py --once     one pass, then exit (exit code 1 if it failed)

Settings come from environment variables (docker-compose.calendar.yml fills them from .env).
"""
import base64
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def env(name, default=""):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


VIKUNJA = env("VIKUNJA_URL", "http://vikunja:3456").rstrip("/") + "/api/v1"
TOKEN = env("CALENDAR_VIKUNJA_TOKEN") or env("VIKUNJA_TOKEN")
RADICALE = env("RADICALE_URL", "http://radicale:5232").rstrip("/")
USER, PASSWORD = env("RADICALE_USER"), env("RADICALE_PASSWORD")
CAL_ID = env("CALENDAR_ID", "vikunja-tasks")
CAL_TITLE = env("CALENDAR_TITLE", "Vikunja tasks")
EVERY = int(env("CALENDAR_SYNC_SECONDS", "300"))
TZ = ZoneInfo(env("CALENDAR_TZ", "UTC"))
LINK_BASE = env("LINK_BASE").rstrip("/")
SKIP = {norm(x) for x in env("CALENDAR_SKIP_PROJECTS", "Inbox").split(",") if x.strip()}
# Local clock times that mean "just a date, no real time" -> shown as all-day events.
ALLDAY = {x.strip() for x in env("CALENDAR_ALLDAY_TIMES", "00:00,12:00,13:00").split(",") if x.strip()}
MINUTES = int(env("CALENDAR_EVENT_MINUTES", "30"))
STATE = Path(env("STATE_FILE", "/state/calendar.json"))
PREFIX = "vikunja-task-"


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def request(method, url, body=None, headers=None, auth=None, timeout=30):
    h = dict(headers or {})
    if auth:
        h["Authorization"] = auth
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# ---------------------------------------------------------------- Vikunja (read only)
def vikunja(path):
    status, data = request("GET", VIKUNJA + path, headers={"Accept": "application/json"}, auth=f"Bearer {TOKEN}")
    if status != 200:
        raise RuntimeError(f"Vikunja {path.split('?')[0]}: HTTP {status}")
    return json.loads(data or b"null") or []


def all_tasks():
    # Newer Vikunja lists every task at /tasks; older versions use /tasks/all
    # (which newer ones answer with HTTP 400 because they read "all" as a task id).
    bases, page, out = ["/tasks", "/tasks/all"], 1, []
    while page <= 100:
        try:
            batch = vikunja(f"{bases[0]}?per_page=50&page={page}")
        except RuntimeError as e:
            if page == 1 and len(bases) > 1 and any(f"HTTP {c}" in str(e) for c in (400, 404, 405)):
                bases.pop(0)
                continue
            raise
        out += batch
        if len(batch) < 50:
            break
        page += 1
    return out


def parse_time(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.year < 1900:  # Vikunja's "no date" is 0001-01-01
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- iCalendar
def esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n"))


def fold(line):
    """Lines longer than 75 bytes are folded (RFC 5545)."""
    parts, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 75:
            parts.append(cur)
            cur, size = " " + ch, 1 + n
        else:
            cur += ch
            size += n
    parts.append(cur)
    return "\r\n".join(parts)


def plain(text):
    """Vikunja descriptions are HTML."""
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", text or "")
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def when(due):
    """('day', date) for date-only deadlines, ('time', utc datetime) for real times."""
    if (due.hour, due.minute, due.second) == (17, 0, 0):  # time Docket's inbox helper uses for date-only deadlines
        return "day", due.date()
    local = due.astimezone(TZ)
    if local.strftime("%H:%M") in ALLDAY:
        return "day", local.date()
    return "time", due


def make_ics(task, project):
    due = parse_time(task.get("due_date"))
    kind, at = when(due)
    stamp = (parse_time(task.get("updated")) or parse_time(task.get("created")) or due).astimezone(timezone.utc)
    stamp = stamp.strftime("%Y%m%dT%H%M%SZ")
    labels = [l.get("title", "") for l in (task.get("labels") or []) if l.get("title")]
    link = f"{LINK_BASE}/tasks/{task['id']}" if LINK_BASE else ""
    desc = [f"Project: {project}"]
    if labels:
        desc.append("Labels: " + ", ".join(labels))
    body = plain(task.get("description"))
    if body:
        desc += ["", body[:600] + ("..." if len(body) > 600 else "")]
    if link:
        desc += ["", link]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Docket//Vikunja calendar sync//EN", "BEGIN:VEVENT",
             f"UID:{PREFIX}{task['id']}@docket", f"DTSTAMP:{stamp}", f"LAST-MODIFIED:{stamp}"]
    if kind == "day":
        lines += [f"DTSTART;VALUE=DATE:{at:%Y%m%d}", f"DTEND;VALUE=DATE:{at + timedelta(days=1):%Y%m%d}"]
    else:
        end = at + timedelta(minutes=MINUTES)
        lines += [f"DTSTART:{at.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}", f"DTEND:{end.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"]
    lines += [f"SUMMARY:{esc(task.get('title') or '(untitled)')}",
              f"DESCRIPTION:{esc(chr(10).join(desc))}",
              "CATEGORIES:" + ",".join(esc(c) for c in [project] + labels),
              "TRANSP:TRANSPARENT"]  # a deadline should not make you look busy
    if link:
        lines.append(f"URL:{link}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


# ---------------------------------------------------------------- Radicale (CalDAV)
AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
CAL_URL = f"{RADICALE}/{urllib.parse.quote(USER)}/{urllib.parse.quote(CAL_ID)}/"
PROPFIND = b'<?xml version="1.0"?><propfind xmlns="DAV:"><prop><getetag/></prop></propfind>'
MKCALENDAR = f"""<?xml version="1.0" encoding="UTF-8"?>
<C:mkcalendar xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:set><D:prop>
    <D:displayname>{html.escape(CAL_TITLE)}</D:displayname>
    <C:supported-calendar-component-set><C:comp name="VEVENT"/></C:supported-calendar-component-set>
  </D:prop></D:set>
</C:mkcalendar>""".encode()
XML = {"Content-Type": "application/xml; charset=utf-8"}


def ensure_calendar():
    status, _ = request("PROPFIND", CAL_URL, PROPFIND, {**XML, "Depth": "0"}, AUTH)
    if status == 207:
        return
    if status == 401:
        raise RuntimeError("Radicale: wrong RADICALE_USER / RADICALE_PASSWORD")
    if status != 404:
        raise RuntimeError(f"Radicale: unexpected HTTP {status} for the calendar")
    status, data = request("MKCALENDAR", CAL_URL, MKCALENDAR, XML, AUTH)
    if status not in (200, 201):
        raise RuntimeError(f"Radicale: could not create the calendar (HTTP {status}) {data[:200]!r}")
    log(f"created calendar '{CAL_TITLE}'")


def remote_names():
    status, data = request("PROPFIND", CAL_URL, PROPFIND, {**XML, "Depth": "1"}, AUTH)
    if status != 207:
        raise RuntimeError(f"Radicale: could not list the calendar (HTTP {status})")
    names = set()
    for r in ET.fromstring(data).iter("{DAV:}response"):
        path = urllib.parse.unquote(urllib.parse.urlparse(r.findtext("{DAV:}href") or "").path)
        if path.endswith(".ics"):
            names.add(path.rsplit("/", 1)[1])
    return names


def put(name, ics):
    status, data = request("PUT", CAL_URL + urllib.parse.quote(name), ics.encode(),
                           {"Content-Type": "text/calendar; charset=utf-8"}, AUTH)
    if status not in (200, 201, 204):
        raise RuntimeError(f"Radicale: PUT {name} failed (HTTP {status}) {data[:200]!r}")


def delete(name):
    status, _ = request("DELETE", CAL_URL + urllib.parse.quote(name), auth=AUTH)
    if status not in (200, 204, 404):
        raise RuntimeError(f"Radicale: DELETE {name} failed (HTTP {status})")


# ---------------------------------------------------------------- sync
def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def sync_once():
    ensure_calendar()  # first, so the phone can find the calendar even if Vikunja is not ready yet
    projects = {p["id"]: p for p in vikunja("/projects?per_page=200")}
    wanted, skipped = {}, 0
    for t in all_tasks():
        p = projects.get(t.get("project_id"))
        due = parse_time(t.get("due_date"))
        if t.get("done") or not due:
            continue
        if not p or p.get("is_archived") or norm(p.get("title")) in SKIP:
            skipped += 1
            continue
        wanted[f"{PREFIX}{t['id']}.ics"] = make_ics(t, p.get("title") or "")

    remote = {n for n in remote_names() if n.startswith(PREFIX)}
    state = load_state()
    added = changed = 0
    new_state = {}
    for name, ics in sorted(wanted.items()):
        digest = hashlib.sha1(ics.encode()).hexdigest()
        new_state[name] = digest
        if name not in remote:
            put(name, ics)
            added += 1
        elif state.get(name) != digest:
            put(name, ics)
            changed += 1
    removed = 0
    for name in sorted(remote - set(wanted)):
        delete(name)
        removed += 1
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(new_state))
    tmp.replace(STATE)
    if added or changed or removed:
        log(f"calendar updated: {len(wanted)} events (+{added} new, ~{changed} changed, -{removed} removed)")
    return len(wanted)


def main():
    if not (TOKEN and USER and PASSWORD):
        sys.exit("Set VIKUNJA_TOKEN, RADICALE_USER and RADICALE_PASSWORD in .env")
    once = "--once" in sys.argv
    log(f"calendar sync started (every {EVERY}s, timezone {TZ.key}, skipping projects: {', '.join(sorted(SKIP)) or 'none'})")
    while True:
        try:
            n = sync_once()
            if once:
                log(f"done: {n} events in the calendar")
        except Exception as e:  # keep going: Vikunja or Radicale may just not be up yet
            log("sync failed:", e)
            if once:
                sys.exit(1)
        if once:
            return
        time.sleep(EVERY)


if __name__ == "__main__":
    main()
