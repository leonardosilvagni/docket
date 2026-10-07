#!/usr/bin/env bash
# Research mode: one launcher for the whole note-taking setup.
#
#   research-mode.sh         open everything: Vikunja + inbox helper (Docker), LM Studio,
#                            OpenWhispr, and the Vikunja board in your browser.
#                            Quit OpenWhispr and everything closes again (the last notes
#                            are turned into tickets first).
#   research-mode.sh stop    emergency stop, if something was left running.
set -u
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec >>"$DIR/research-mode.log" 2>&1
echo "=== $(date '+%F %T') research mode ${1:-start}"

say() { echo "$1"; command -v notify-send >/dev/null && notify-send -a "Research mode" "Research mode" "$1"; }

# Docker without sudo if you're in the docker group, otherwise a password dialog
if docker info >/dev/null 2>&1; then DOCKER=(docker); else DOCKER=(pkexec docker); fi
dc() { "${DOCKER[@]}" compose --project-directory "$DIR" "$@"; }

LMS="$(command -v lms || echo "$HOME/.lmstudio/bin/lms")"
lm_stop() {
  # ask LM Studio to stop politely (killing it makes it report a crash)
  [ -x "$LMS" ] || return 0
  "$LMS" unload --all
  "$LMS" server stop
  "$LMS" daemon down 2>/dev/null || true   # newer versions: also stop the background service
}

if [ "${1:-}" = "stop" ]; then
  dc stop
  lm_stop
  say "Everything stopped."
  exit 0
fi

# OpenWhispr: find the installed app (command in PATH, its menu entry, or /opt), else an AppImage
OW=()
[ -x /opt/OpenWhispr/open-whispr ] && OW=(/opt/OpenWhispr/open-whispr)
[ ${#OW[@]} = 0 ] && for c in open-whispr openwhispr OpenWhispr; do command -v "$c" >/dev/null && { OW=("$c"); break; }; done
if [ ${#OW[@]} = 0 ]; then
  for f in /usr/share/applications/*.desktop /usr/local/share/applications/*.desktop; do
    grep -qi "^Name=.*whispr" "$f" 2>/dev/null || continue
    e="$(grep -m1 '^Exec=' "$f" | sed 's/^Exec=//; s/ %[a-zA-Z]//g; s/^"\(.*\)"$/\1/')"
    [ -n "$e" ] && { read -r -a OW <<<"$e"; break; }
  done
fi
if [ ${#OW[@]} = 0 ]; then
  b="$(ls -d /opt/*[Ww]hispr*/open-whispr /opt/*[Ww]hispr*/openwhispr 2>/dev/null | head -1)"
  [ -z "$b" ] && b="$(ls -t "$HOME"/installs/OpenWhispr-*.AppImage 2>/dev/null | head -1)"
  [ -n "$b" ] && OW=("$b")
fi
echo "OpenWhispr command: ${OW[*]:-none}"
[ ${#OW[@]} -gt 0 ] || { say "OpenWhispr not found"; exit 1; }
# only the app itself counts (its helper processes can linger after it quits)
pgrep -x open-whispr >/dev/null && { say "OpenWhispr is already running"; exit 0; }
pkill -f "/opt/OpenWhispr/resources/bin/" 2>/dev/null   # clear leftovers from a previous run

# ---- start
dc up -d || { say "Could not start Vikunja. Is Docker running?"; exit 1; }
# start LM Studio's server on the port the helper expects (LLM_URL in .env, default 1234)
LM_PORT="$(grep -oP '^LLM_URL=.*:\K[0-9]+' "$DIR/.env" 2>/dev/null || echo 1234)"
if [ -x "$LMS" ]; then "$LMS" server start --port "$LM_PORT"; else echo "LM Studio CLI (lms) not found"; fi
for i in $(seq 30); do curl -fs http://127.0.0.1/api/v1/info >/dev/null && break; sleep 1; done
HOST="$(grep -oP '^VIKUNJA_HOST=\K\S+' "$DIR/.env" 2>/dev/null || echo research.localhost)"
xdg-open "http://$HOST" >/dev/null 2>&1 &
say "Started. Quit OpenWhispr (tray icon → Quit) to close everything."

"${OW[@]}"   # waits here until OpenWhispr quits

# ---- after OpenWhispr closes: finish the last notes, then close everything
pkill -f "/opt/OpenWhispr/resources/bin/" 2>/dev/null   # OpenWhispr's background helpers
say "Closing: turning the last notes into tickets first..."
dc stop inbox-helper
dc run --rm --no-deps inbox-helper python -u /app/helper.py --drain || echo "drain failed"
dc stop
lm_stop
say "Everything closed. New suggestions will be in the Inbox next time."
