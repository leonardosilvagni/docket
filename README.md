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

Nothing leaves your computer. Vikunja and LM Studio only listen on `127.0.0.1`.

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
| `VIKUNJA_HOST` | `docket.localhost` | Board address. Any `*.localhost` name works without a hosts entry; other names need `127.0.0.1 <name>` in `/etc/hosts` |
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

Restart the helper after changing `.env`: `docker compose restart inbox-helper`.

## Files

| File | Purpose |
|---|---|
| `setup.sh` | One-time Linux setup |
| `docker-compose.yml` | Vikunja + inbox helper |
| `docker-compose.windows.yml` | Windows (Docker Desktop) override |
| `.env.example` | Settings template |
| `helper/helper.py` | The inbox helper |
| `docket.sh`, `docket.desktop` | Linux launcher and app-menu entry |
| `docket.ps1` | Windows launcher |

Not in git (see `.gitignore`): `.env` (tokens), `db/` and `files/` (your tasks), `helper/state/`, logs.

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
| Approved card doesn't move | The "Suggested project" line in its description must match a project name exactly |

To re-run a note: `touch ~/Documents/meeting-notes/<note>.md`.

## Moving to another computer

Your tasks live in `db/` and `files/`, which are not in git. Stop everything (quit OpenWhispr), then copy the repo folder **including** `.env`, `db/` and `files/` to the new machine, install the apps (step 1), run `bash setup.sh` (it keeps your `.env`), and download the model again. Keep `VIKUNJA_JWTSECRET` the same so your logins stay valid.

Vikunja → Settings → **Export** gives an extra backup of all your data as a zip.

## Privacy

Recordings, notes, the model and your tasks stay on your computer. Keep `.env` out of git and shared folders. Get consent before recording people, and check your institution's rules before recording or storing research details.
