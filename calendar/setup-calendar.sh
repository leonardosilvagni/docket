#!/usr/bin/env bash
# OPTIONAL: show your Vikunja due dates in your phone's calendar (via DAVx5).
# Run it from anywhere; safe to run again (it never overwrites your settings):
#   bash calendar/setup-calendar.sh
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$DIR"
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
todo() { printf '  \033[33m•\033[0m %s\n' "$1"; }

[ -f .env ] || { echo "No .env yet: run 'bash setup.sh' first."; exit 1; }
getenv() { grep -oP "^$1=\K.*" .env | tail -1 || true; }

echo "Settings"
mkdir -p calendar/data calendar/state
ok "folders calendar/data and calendar/state"

add() {  # add KEY=VALUE to .env unless KEY is already there
  if grep -q "^$1=" .env; then ok "$1 already set"; else printf '%s=%s\n' "$1" "$2" >> .env; ok "added $1 to .env"; fi
}
tz="$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo UTC)"
if ! grep -q '^# --- Calendar' .env; then printf '\n# --- Calendar (optional, see calendar/)\n' >> .env; fi
add RADICALE_USER docket
add RADICALE_PASSWORD "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
add CALENDAR_TZ "$tz"
if grep -q '^COMPOSE_FILE=' .env; then
  grep -q 'calendar/docker-compose.calendar.yml' .env \
    && ok "COMPOSE_FILE already includes the calendar" \
    || todo "COMPOSE_FILE is already set in .env: append :calendar/docker-compose.calendar.yml to it"
else
  printf 'COMPOSE_FILE=docker-compose.yml:calendar/docker-compose.calendar.yml\n' >> .env
  ok "turned the calendar on (COMPOSE_FILE in .env)"
fi
chmod 600 .env

echo "Checks"
[ -n "$(getenv VIKUNJA_TOKEN)" ] && ok "VIKUNJA_TOKEN is set" || todo "set VIKUNJA_TOKEN in .env first (Vikunja > Settings > API Tokens)"
docker info >/dev/null 2>&1 && ok "Docker" || { todo "Docker is not running or you are not in the docker group"; exit 1; }

echo "Starting"
docker compose build calendar-sync >/dev/null && ok "built the calendar image"
docker compose up -d >/dev/null && ok "calendar services are running"
sleep 8
docker compose logs --tail 5 calendar-sync 2>&1 | sed 's/^/    /'

host="$(getenv VIKUNJA_HOST)"
user="$(getenv RADICALE_USER)"
cat <<EOF

Next (once):
  1. On this PC, share the calendar server inside your Tailscale network:
       sudo tailscale serve --bg --https=8443 http://127.0.0.1:5232
     then check it with:  tailscale serve status
  2. On the phone (Tailscale connected), install DAVx5, then: + > "Login with URL and user name"
       Base URL:  https://${host}:8443/
       User name: ${user}
       Password:  RADICALE_PASSWORD from .env
     Pick the "Vikunja tasks" calendar, switch syncing on, and allow the calendar permission.
  3. Open your calendar app; the calendar appears under the DAVx5 account (enable it in the
     app's calendar list if it is hidden).

Tasks with a due date show up within a few minutes of being created or changed.
To turn it off: delete the COMPOSE_FILE line from .env and run 'docker compose down --remove-orphans'.
EOF
