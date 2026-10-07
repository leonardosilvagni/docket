#!/usr/bin/env bash
# One-time setup on a new Linux machine. Safe to run again: it never overwrites your .env.
#   bash setup.sh
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$DIR"
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
todo() { printf '  \033[33m•\033[0m %s\n' "$1"; TODO=1; }
TODO=0

echo "Folders and settings"
mkdir -p db files helper/state
if [ ! -f .env ]; then
  cp .env.example .env
  secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed -i "s|^VIKUNJA_JWTSECRET=.*|VIKUNJA_JWTSECRET=$secret|" .env
  sed -i "s|^NOTES_DIR=.*|NOTES_DIR=$HOME/Documents/meeting-notes|" .env
  chmod 600 .env
  ok "created .env with a new Vikunja secret (edit OWNER and LLM_MODEL in it)"
else
  ok ".env already exists, left unchanged"
fi
notes="$(grep -oP '^NOTES_DIR=\K.*' .env || true)"
[ -n "$notes" ] && mkdir -p "$notes" && ok "meeting notes folder: $notes"

echo "App menu"
mkdir -p "$HOME/.local/share/applications"
sed "s|REPO|$DIR|g" research-mode.desktop > "$HOME/.local/share/applications/research-mode.desktop"
ok "Research mode added to the app menu"

echo "Checks"
command -v python3 >/dev/null && ok "python3" || todo "install python3"
if ! command -v docker >/dev/null; then
  todo "install Docker: sudo apt install docker.io docker-compose-v2"
elif ! docker info >/dev/null 2>&1; then
  todo "allow Docker without sudo: sudo usermod -aG docker \$USER, then reboot"
else
  ok "Docker"
fi
if command -v lms >/dev/null || [ -x "$HOME/.lmstudio/bin/lms" ]; then ok "LM Studio (lms)"
else todo "install LM Studio, then run ~/.lmstudio/bin/lms bootstrap"; fi
if [ -x /opt/OpenWhispr/open-whispr ] || command -v open-whispr >/dev/null; then ok "OpenWhispr"
else todo "install OpenWhispr (.deb from its GitHub releases)"; fi
command -v pactl >/dev/null && ok "pactl (meeting detection)" || todo "sudo apt install pulseaudio-utils"

host="$(grep -oP '^VIKUNJA_HOST=\K\S+' .env || echo research.localhost)"
case "$host" in
  *.localhost) ok "board address: http://$host (no hosts entry needed)" ;;
  *) if getent hosts "$host" | grep -q '127.0.0.1'; then ok "board address: http://$host"
     else todo "add the board address: echo \"127.0.0.1 $host\" | sudo tee -a /etc/hosts"; fi ;;
esac

if docker info >/dev/null 2>&1; then
  echo "Starting Vikunja"
  docker compose up -d vikunja >/dev/null && ok "Vikunja is running at http://$host"
fi

echo
echo "Next:"
echo "  1. Open http://$host, create your account."
echo "  2. In Vikunja: Settings > API Tokens > create one; paste it into .env as VIKUNJA_TOKEN."
echo "  3. In LM Studio: download your model, start nothing else; set LLM_MODEL in .env to its name (lms ls)."
echo "     If LM Studio's server requires an API token, put it in .env as LLM_API_KEY (and in OpenWhispr)."
echo "  4. In OpenWhispr: AI provider = LM Studio (http://127.0.0.1:1234/v1); Notes > disk mirroring = $notes"
echo "  5. Start 'Research mode' from the app menu."
[ "$TODO" = 1 ] && echo "Fix the • items above first, then run this script again."
exit 0
