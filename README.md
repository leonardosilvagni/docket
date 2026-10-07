# Research mode

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
| **Research mode** | Launcher: opens everything, and closes everything when you quit OpenWhispr |

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
git clone <repo-url> ~/installs/research-mode
cd ~/installs/research-mode
bash setup.sh
```

`setup.sh` creates `.env` with a new secret, creates the notes folder (`~/Documents/meeting-notes`), adds **Research mode** to the app menu, checks that everything is installed, and starts Vikunja. It lists anything still missing; fix it and run it again.

**3. Finish the settings** (the script prints these steps too)

1. Open **http://research.localhost**, create your Vikunja account.
2. Vikunja → Settings → **API Tokens** → create one → put it in `.env` as `VIKUNJA_TOKEN`.
3. In `.env`, set `OWNER` (your name) and `LLM_MODEL` (exactly as `lms ls` shows it). If LM Studio's server requires an API token, set `LLM_API_KEY`.
4. OpenWhispr settings: AI provider **LM Studio** at `http://127.0.0.1:1234/v1` (plus the LM Studio token, if any); **Notes → disk mirroring** to the same folder as `NOTES_DIR`.

**4. Use it**

Start **Research mode** from the app menu. Record meetings in OpenWhispr. A few minutes after a note is saved, cards appear in **Vikunja → Inbox → Suggested**. Drag them to **Approved** (they move to their project) or **Rejected**. Quit OpenWhispr from its tray icon and everything closes.

## Set up on Windows (untested)

Install Docker Desktop (WSL 2), LM Studio and OpenWhispr for Windows. Then, in the repo folder:

1. `copy .env.example .env` and fill it in by hand: generate `VIKUNJA_JWTSECRET` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`, set `NOTES_DIR` with forward slashes (`C:/Users/you/Documents/meeting-notes`) and `LLM_URL=http://host.docker.internal:1234/v1`.
2. Create the folders `db`, `files`, `helper\state`.
3. Start once with both compose files: `docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d vikunja`, then create your account and token as above.
4. Check the OpenWhispr path at the top of `research-mode.ps1`, then make a desktop shortcut to
   `powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File "<repo>\research-mode.ps1"`.

## Settings (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `VIKUNJA_HOST` | `research.localhost` | Board address. Any `*.localhost` name works without a hosts entry; other names need `127.0.0.1 <name>` in `/etc/hosts` |
| `VIKUNJA_JWTSECRET` | (generated) | Signs Vikunja logins. Keep it the same when moving machines |
| `VIKUNJA_TOKEN` | | Vikunja API token for the helper. Needs read/create/update on tasks; no delete |
| `NOTES_DIR` | `~/Documents/meeting-notes` | Folder OpenWhispr writes notes to |
| `OWNER` | | Whose tasks these are; every action item is assigned to this person |
| `LLM_URL` | `http://127.0.0.1:1234/v1` | LM Studio server |
| `LLM_MODEL` | `qwen3.5-9b` | Model name as `lms ls` shows it |
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
| `research-mode.sh`, `research-mode.desktop` | Linux launcher and app-menu entry |
| `research-mode.ps1` | Windows launcher |

Not in git (see `.gitignore`): `.env` (tokens), `db/` and `files/` (your tasks), `helper/state/`, logs.

## Troubleshooting

Two logs tell you almost everything:

```bash
docker compose logs --tail 30 inbox-helper    # what the helper did with each note
tail -40 research-mode.log                     # what the launcher did
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
