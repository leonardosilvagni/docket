# Docket

A local, subscription-free setup that records meetings, turns them into suggested tasks with an AI model running on your own computer, and lets you approve them on a Kanban board.

```
OpenWhispr ──note──▶ meeting-notes/ ──▶ inbox helper ──▶ LM Studio (local model)
                                             │
                                             ▼
                          Vikunja: Inbox → Suggested → Approved → project To Do
```

| Part | What it does |
|---|---|
| **OpenWhispr** | Records and transcribes meetings on your computer, saves notes as Markdown |
| **LM Studio** | Runs the model (tested: Qwen3.5 9B) and serves it at `127.0.0.1:1234` |
| **Vikunja** | Task boards (SQLite, Docker) |
| **Inbox helper** | `helper/helper.py`: new note → suggested cards; approved cards → their project. Python standard library, ~15 MB RAM |
| **Launcher** (`docket.sh`) | Opens everything, and closes everything when you quit OpenWhispr |

Nothing leaves your computer. Vikunja and LM Studio only listen on `127.0.0.1`. The only way in from another device is through your own Tailscale network (see [Use it from your phone](#use-it-from-your-phone-tailscale)).

## Set up on a new Linux machine

**1. Install the apps**

```bash
sudo apt install git docker.io docker-compose-v2 pulseaudio-utils python3
sudo usermod -aG docker $USER        # then reboot (logging out is often not enough)
```

- **LM Studio**: install it, choose the Vulkan (AMD) or CUDA (NVIDIA) runtime, download a model (e.g. Qwen3.5 9B, Q5_K_M). Run `~/.lmstudio/bin/lms bootstrap` once so `lms` works in the terminal.
- **OpenWhispr**: install the `.deb` from its GitHub releases (`sudo apt install ./OpenWhispr-*-linux-amd64.deb`).

**2. Get this repo and run the setup script**

```bash
git clone <repo-url> ~/installs/docket
cd ~/installs/docket
bash setup.sh
```

`setup.sh` creates `.env` with a new secret, creates the notes folder (`~/Documents/meeting-notes`), adds **Docket** to the app menu, checks that everything is installed, and starts Vikunja. It lists anything still missing; fix it and run it again.

**3. Finish the settings** (the script prints these steps too)

1. Open **http://docket.localhost**, create your Vikunja account.
2. Vikunja → Settings → **API Tokens** → create one → put it in `.env` as `VIKUNJA_TOKEN`.
3. In `.env`, set `OWNER` (your name) and `LLM_MODEL` (exactly as `lms ls` shows it). If LM Studio's server requires an API token, set `LLM_API_KEY`.
4. OpenWhispr settings: AI provider **LM Studio** at `http://127.0.0.1:1234/v1` (plus the LM Studio token, if any); **Notes → disk mirroring** to the same folder as `NOTES_DIR`.

**4. Describe your projects and labels** (once, then whenever you add one)

The model chooses a project and labels for each task from what you have in Vikunja, so give it something to go on:

- **Project descriptions:** open each project → **⋯ → Edit → Description**. Write 2–3 keyword-rich sentences: what it is, typical activities, distinctive terms, people who come up. The model sees the first 400 characters. Example:
  > Thesis project: lateral intercostal nerve transfer to the stomach for gastroparesis, in rats. Rat surgeries, tissue clearing, histology (NF-200, synaptophysin), gastric motility and stimulation experiments. Usually discussed with Alan and Dan.
- **Labels:** create labels for the kinds of work you do (e.g. *Logistics*, *Literature research*, *Surgeries and data acquisition*, *Thesis writing*). The model attaches 1–2 of them per task and never invents new ones.

## Daily use

**Start:** open **Docket** from the app menu. It starts LM Studio's server, Vikunja and the inbox helper, opens OpenWhispr, and opens the board in your browser.

**Meetings:** record in OpenWhispr as usual. Each note it saves to the notes folder is picked up automatically. You can also drop any transcript or notes file (`.md` or `.txt`) into the folder yourself. Put the date in the file name (`2026-10-07 lab meeting.md`) so "Friday" or "next Monday" resolve to the right dates.

**Suggestions:** a few minutes after a note is saved (about 1 minute with `LLM_THINKING=0`, 5–8 with `auto`), cards appear in **Inbox → Suggested** (open the Inbox project and pick the **Kanban** view). Each card has:

- a short title and a 1–4 sentence description of what to do
- a due date and priority, if they were said in the meeting
- a **Suggested project** line, the label *AI suggested*, and 1–2 of your own labels
- the meeting note it came from

Every action item from the meeting is suggested, whoever it was for. You decide which are yours.

**Reviewing:** for each card in **Suggested**:

| You want to… | Do this | What happens |
|---|---|---|
| Keep it | Drag it to **Approved** | Within a minute (`POLL_SECONDS`) it moves to its project's **To Do** column, keeping its labels |
| Keep it, in another project | Edit the **Suggested project** line to another project's exact name, then drag to **Approved** | It moves to that project |
| Change details | Edit the title, description, date or labels, then approve | Your edits are kept |
| Drop it | Drag it to **Rejected** | It's marked done and stays in the Rejected column. Nothing is deleted |
| Undo a rejection | Drag it back to **Suggested** or **Approved** | It's open again (and moved, if approved) |

Rejected cards are hidden from lists and overviews but stay in the Kanban column. To clean up, open a card → **Delete** (permanent). The helper itself never deletes anything.

If an approved card stays in **Approved** with a "Could not move" note, its Suggested project line doesn't match any project name (for example after you renamed a project). Fix the name; it moves at the next check.

**Working on tasks:** use each project's board as normal: **Backlog → To Do → Doing → Done**.

**Stop:** quit OpenWhispr from its tray icon (closing the window may only hide it). Docket turns any remaining notes into suggestions first, then stops the helper, Vikunja and LM Studio. With reasoning on, this can take a few minutes after a meeting; let it finish. Suggestions appear in the Inbox the next time you open Docket.

**Re-run a note** (e.g. after editing it or changing settings): `touch ~/Documents/meeting-notes/<note>.md`. To see what the helper is doing: `docker compose logs -f inbox-helper`.

**Faster or smarter:** `LLM_THINKING=0` in `.env` gives suggestions in about a minute; `auto` (default) reasons briefly first. Restart the helper after changing it: `docker compose restart inbox-helper`.

## Use it from your phone (Tailscale)

Vikunja is bound to `127.0.0.1:80`, so nothing on your LAN or the internet can reach it directly. Tailscale (a private network between your own devices) is the only way in from the phone. Current setup:

| Item | Value |
|---|---|
| PC (host) | `leo-pc`, Tailscale name `leo-pc.taila60bcc.ts.net` |
| Address to use, on PC and phone | **https://leo-pc.taila60bcc.ts.net** |
| Port | Vikunja stays on `127.0.0.1:80`; Tailscale serves it on 443 |

**What was done**

1. Installed Tailscale on the PC and on the phone, signed in to the same account.
2. In the Tailscale admin console → **DNS**: MagicDNS on, and **HTTPS Certificates** enabled.
3. On the PC: `sudo tailscale serve --bg 80`. This publishes Vikunja at the `https://…ts.net` address above, inside the tailnet only. `--bg` keeps it running across reboots; `tailscale serve status` shows it.
4. In `.env`: `VIKUNJA_HOST=leo-pc.taila60bcc.ts.net` (name only, no `https://`, no trailing slash).
5. In `docker-compose.yml`: `VIKUNJA_SERVICE_PUBLICURL` now starts with `https://` (it was `http://`).
6. `docker compose up -d` to recreate Vikunja with the new public URL.

**Why the public URL matters.** Vikunja's web page takes its API address from `VIKUNJA_SERVICE_PUBLICURL`. If you open the board under any other name, the page loads but login fails with "network error", or Vikunja says "use the Vikunja installation at …". Vikunja can only be reached under one name at a time, so use the `.ts.net` address everywhere (PC browser, phone, bookmarks) instead of `docket.localhost`.

**On the phone:** Tailscale must be connected (Android allows one active VPN at a time, so another VPN app such as Surfshark has to be off), then open the address in Chrome. Use **Add to Home Screen** to install it as an app; this needs the HTTPS address. The PC must be on, awake and running Docker.

**Check it is applied** (from the repo folder):

```bash
docker compose config | grep PUBLICURL
docker inspect vikunja --format '{{range .Config.Env}}{{println .}}{{end}}' | grep PUBLICURL
```

Both should print `https://leo-pc.taila60bcc.ts.net/`.

**If you rename the PC or the tailnet:** the address changes. Update `VIKUNJA_HOST`, run `docker compose up -d`, check `tailscale serve status` (re-run `sudo tailscale serve --bg 80` if the new address is missing), and sign in again on the phone. The machine name can be changed in the admin console or with `tailscale set --hostname=<name>`. The tailnet name can only be changed to one of the generated options (admin console → DNS → Rename tailnet).

**Going back to local-only** (`docket.localhost`): set `VIKUNJA_HOST=docket.localhost` and change `https://` back to `http://` in the `VIKUNJA_SERVICE_PUBLICURL` line of `docker-compose.yml`, then `docker compose up -d`.

## Optional: due dates in your phone's calendar

Not needed for anything above. It shows every open Vikunja task that has a due date as an event in a calendar on your phone. One way: Vikunja stays the source of truth, and editing an event in the calendar app does not change the task.

```
Vikunja ──(read only)──▶ calendar-sync ──▶ Radicale (CalDAV server) ──Tailscale──▶ DAVx5 ──▶ phone calendar
```

Two small extra containers, all in the `calendar/` folder (about 100 MB of disk, roughly 50 MB of RAM together). It needs the phone access from the Tailscale section above.

**Turn it on** (Linux):

```bash
bash calendar/setup-calendar.sh
```

It creates a calendar user and password in `.env`, adds `COMPOSE_FILE=docker-compose.yml:calendar/docker-compose.calendar.yml` (that line is what turns it on), builds the image and starts both services. It then prints the remaining steps:

1. On the PC: `sudo tailscale serve --bg --https=8443 http://127.0.0.1:5232` (check with `tailscale serve status`).
2. On the phone: install **DAVx5** → **+** → *Login with URL and user name*. Base URL `https://leo-pc.taila60bcc.ts.net:8443/`, user and password from `.env` (`RADICALE_USER`, `RADICALE_PASSWORD`). Tick the **Vikunja tasks** calendar, allow the calendar permission, and set a sync interval.
3. Your calendar app (Google Calendar, Fossify, …) lists it under the DAVx5 account. Enable it there if it is hidden.

**What shows up**

- Open tasks with a due date, in every project except the ones in `CALENDAR_SKIP_PROJECTS` (default `Inbox`, so unapproved suggestions stay out). Archived projects are left out too.
- A date-only deadline becomes an **all-day** event. A deadline with a real time becomes a 30-minute event starting then. Times in `CALENDAR_ALLDAY_TIMES` (your timezone; default 00:00, 12:00, 13:00) and the 17:00 UTC the inbox helper uses count as "date only".
- Title, project, labels, the first part of the description and a link back to the task are in the event. Events are marked *free*, so a deadline doesn't make you look busy.
- Done, deleted or un-dated tasks disappear from the calendar at the next refresh (`CALENDAR_SYNC_SECONDS`, default 5 minutes).

**Notes**

- It only refreshes while the PC is on (Docket running). With the phone off Tailscale or the PC off, the phone keeps showing the last synced events.
- Vikunja is only read. The sync uses `VIKUNJA_TOKEN`; to be stricter, create a separate token with read access only and put it in `.env` as `CALENDAR_VIKUNJA_TOKEN`.
- Radicale listens on `127.0.0.1` only and needs the user and password. Nothing else is reachable from your network.
- Nothing to back up: the calendar is rebuilt from Vikunja. `calendar/data/` and `calendar/state/` are not in git.
- Logs: `docker compose logs --tail 20 calendar-sync`.
- **Windows** (untested): start with `docker compose -f docker-compose.yml -f docker-compose.windows.yml -f calendar/docker-compose.calendar.yml up -d`, after adding `RADICALE_USER`, `RADICALE_PASSWORD` and `CALENDAR_TZ` to `.env` by hand and creating the folders `calendar\data` and `calendar\state`.
- **Turn it off:** delete the `COMPOSE_FILE` line from `.env`, then `docker compose down --remove-orphans`.

## Set up on Windows (untested)

Install Docker Desktop (WSL 2), LM Studio and OpenWhispr for Windows. Then, in the repo folder:

1. `copy .env.example .env` and fill it in by hand: generate `VIKUNJA_JWTSECRET` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`, set `NOTES_DIR` with forward slashes (`C:/Users/you/Documents/meeting-notes`) and `LLM_URL=http://host.docker.internal:1234/v1`.
2. Create the folders `db`, `files`, `helper\state`.
3. Start once with both compose files: `docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d vikunja`, then create your account and token as above.
4. Check the OpenWhispr path at the top of `docket.ps1`, then make a desktop shortcut to
   `powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File "<repo>\docket.ps1"`.

## Settings (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `VIKUNJA_HOST` | `docket.localhost` | Board address. Must be the name you actually open in the browser. With Tailscale: `leo-pc.taila60bcc.ts.net` (the compose file builds an `https://` public URL from it). For local-only use, any `*.localhost` name works without a hosts entry, but the compose file must use `http://` (see the Tailscale section) |
| `VIKUNJA_JWTSECRET` | (generated) | Signs Vikunja logins. Keep it the same when moving machines |
| `VIKUNJA_TOKEN` | | Vikunja API token for the helper. Needs read/create/update on tasks; no delete |
| `NOTES_DIR` | `~/Documents/meeting-notes` | Folder OpenWhispr writes notes to |
| `OWNER` | | Whose tasks these are; every action item is assigned to this person |
| `LLM_URL` | `http://127.0.0.1:1234/v1` | LM Studio server |
| `LLM_MODEL` | `qwen/qwen3.5-9b` | Model name as `lms ls` shows it |
| `LLM_API_KEY` | | LM Studio token, if its server requires one |
| `LLM_CONTEXT` | `32768` | The helper (re)loads the model with this context length |
| `LLM_THINKING` | `auto` | `auto`: reason up to the budget, then finish from that reasoning. `1`: unlimited. `0`: off (fastest) |
| `LLM_THINK_BUDGET` | `2500` | Reasoning budget in tokens for `auto` |
| `POLL_SECONDS` | `60` | How often the helper checks for new notes and approved cards |
| `PROCESS_EXISTING` | `0` | `1` also processes notes already in the folder on first start |
| `MAX_TRIES` | `2` | Attempts per note before giving up |
| `RADICALE_USER`, `RADICALE_PASSWORD` | | Calendar login (optional calendar; made by `calendar/setup-calendar.sh`) |
| `CALENDAR_TZ` | `UTC` | Your timezone for due times, e.g. `America/New_York` |
| `CALENDAR_SYNC_SECONDS` | `300` | How often the calendar refreshes |
| `CALENDAR_SKIP_PROJECTS` | `Inbox` | Projects left out of the calendar, comma separated |
| `CALENDAR_ALLDAY_TIMES` | `00:00,12:00,13:00` | Due times (your timezone) treated as "date only" → all-day events |
| `CALENDAR_EVENT_MINUTES` | `30` | Length of an event for a task due at a specific time |
| `CALENDAR_VIKUNJA_TOKEN` | | Optional read-only Vikunja token for the calendar (default: `VIKUNJA_TOKEN`) |

Restart the helper after changing `.env`: `docker compose restart inbox-helper`.

## Files

| File | Purpose |
|---|---|
| `setup.sh` | One-time Linux setup |
| `docker-compose.yml` | Vikunja + inbox helper |
| `docker-compose.windows.yml` | Windows (Docker Desktop) override |
| `calendar/` | Optional phone calendar: `setup-calendar.sh`, `docker-compose.calendar.yml`, `sync.py`, `radicale.conf`, `Dockerfile` |
| `.env.example` | Settings template |
| `helper/helper.py` | The inbox helper |
| `docket.sh`, `docket.desktop` | Linux launcher and app-menu entry |
| `docket.ps1` | Windows launcher |

Not in git (see `.gitignore`): `.env` (tokens), `db/` and `files/` (your tasks), `helper/state/`, `calendar/data/`, `calendar/state/`, logs.

## Troubleshooting

Two logs tell you almost everything:

```bash
docker compose logs --tail 30 inbox-helper    # what the helper did with each note
tail -40 docket.log                     # what the launcher did
```

| Log line or symptom | Fix |
|---|---|
| `HTTP 401 ... chat/completions` | LM Studio requires a token: set `LLM_API_KEY` |
| `model ... not found` | Set `LLM_MODEL` exactly as `lms ls` shows it |
| `connection problem ... retrying in 30s` | LM Studio's server isn't running yet; it retries by itself. Check `lms server status` |
| `finish_reason=length` | Context too small for the meeting: raise `LLM_CONTEXT` |
| `giving up` on a note | Fix the cause above, then `touch` the note to retry |
| Asked for a password on start | You're not in the `docker` group yet: reboot after `usermod` |
| Board address doesn't open | Use a `*.localhost` name, or check `/etc/hosts`; try a private window if the browser forces https |
| "Network error" at login, or "use the Vikunja installation at …" | The address you opened doesn't match the public URL. Open `https://leo-pc.taila60bcc.ts.net`, check `VIKUNJA_HOST` in `.env`, run `docker compose up -d`, then clear the site data in the phone browser |
| Page doesn't open on the phone | Tailscale must be connected on the phone (other VPNs off) and on the PC; check `tailscale serve status` on the PC |
| Calendar on the phone is empty or stale | `docker compose logs --tail 20 calendar-sync` shows what it did; check DAVx5 can reach `https://<name>.ts.net:8443/` (Tailscale on, `tailscale serve status`), and that the task has a due date and isn't in the Inbox |
| Approved card doesn't move | The "Suggested project" line in its description must match a project name exactly |

To re-run a note: `touch ~/Documents/meeting-notes/<note>.md`.

## Moving to another computer

Your tasks live in `db/` and `files/`, which are not in git. Stop everything (quit OpenWhispr), then copy the repo folder **including** `.env`, `db/` and `files/` to the new machine, install the apps (step 1), run `bash setup.sh` (it keeps your `.env`), and download the model again. Keep `VIKUNJA_JWTSECRET` the same so your logins stay valid.

Vikunja → Settings → **Export** gives an extra backup of all your data as a zip.

## Privacy

Recordings, notes, the model and your tasks stay on your computer. Keep `.env` out of git and shared folders. Get consent before recording people, and check your institution's rules before recording or storing research details.
