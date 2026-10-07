# Research mode

A local, subscription-free setup that records meetings, turns them into suggested tasks with an AI model running on your own computer, and lets you approve them on a Kanban board.

```
OpenWhispr ──note──▶ meeting-notes/ ──▶ inbox helper ──▶ LM Studio (local model)
                                             │
                                             ▼
                          Vikunja: Inbox → Suggested → Approved → project To Do
```

- **OpenWhispr** records and transcribes meetings and saves notes as Markdown.
- **Inbox helper** (`helper/helper.py`, Python standard library, ~15 MB RAM) sends each new note to LM Studio and creates suggested cards in Vikunja's Inbox. Cards you drag to *Approved* move to their project; *Rejected* cards are marked done.
- **LM Studio** runs the model (tested with Qwen3.5 9B) on your machine.
- **Vikunja** is the task board (SQLite, runs in Docker).
- **Research mode** (`research-mode.sh` / `research-mode.ps1`) opens everything together and closes everything when you quit OpenWhispr.

Nothing leaves your computer. Vikunja and LM Studio only listen on `127.0.0.1`.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Vikunja + inbox helper |
| `docker-compose.windows.yml` | Windows (Docker Desktop) override |
| `.env.example` | Settings template. Copy to `.env` (never commit it) |
| `helper/helper.py` | The inbox helper |
| `research-mode.sh`, `research-mode.desktop` | Linux launcher and app-menu entry |
| `research-mode.ps1` | Windows launcher (untested) |

Not in the repo (see `.gitignore`): `.env`, `db/`, `files/`, `helper/state/`, logs.

## Setup (Linux)

1. Install **Docker** and add yourself to the `docker` group, then reboot:
   `sudo apt install docker.io docker-compose-v2 && sudo usermod -aG docker $USER`
2. Install **LM Studio**, pick the Vulkan (AMD) or CUDA (NVIDIA) runtime, download a model (e.g. Qwen3.5 9B). In the model's settings set **Context Length to 16384–32768**. In *Developer → Server Settings* turn on Just-in-Time loading and auto-unload. Check that `lms status` works.
3. Install **OpenWhispr**. Set its AI provider to LM Studio (`http://127.0.0.1:1234/v1`) and Notes → disk mirroring to your notes folder. On Linux also `sudo apt install pulseaudio-utils`.
4. Configure:
   ```bash
   git clone <this repo> ~/installs/research-mode && cd ~/installs/research-mode
   mkdir -p db files helper/state ~/Documents/meeting-notes
   cp .env.example .env && chmod 600 .env
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as VIKUNJA_JWTSECRET
   nano .env
   docker compose up -d vikunja
   ```
5. Open `http://research.localhost` (or your `VIKUNJA_HOST`), create your account, create an API token (Settings → API Tokens), and put it in `.env` as `VIKUNJA_TOKEN`.
6. Launcher: in `research-mode.desktop` replace `REPO` with this folder's full path, then `cp research-mode.desktop ~/.local/share/applications/`.
7. Start **Research mode** from the app menu.

## Setup (Windows)

Same steps with Docker Desktop, LM Studio and OpenWhispr for Windows. In `.env` set `LLM_URL=http://host.docker.internal:1234/v1` and a Windows `NOTES_DIR` with forward slashes. Start with both compose files (`docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d`), and use `research-mode.ps1` as the launcher; check the OpenWhispr path at its top first.

## Check that it works

```bash
docker compose logs -f inbox-helper
```

After a note is saved you should see `asking <model> ...`, then `suggested: ...` lines a few minutes later. Errors say what to fix (missing LM Studio token, wrong model name, context too small).

## Moving to another computer

Stop Vikunja, copy the whole folder including `.env`, `db/` and `files/`, reinstall the three apps, and download the model again. Your account and tasks are in `db/`.
