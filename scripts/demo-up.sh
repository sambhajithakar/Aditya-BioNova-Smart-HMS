#!/usr/bin/env bash
# Start the SYNTHETIC-DATA demo of Aditya BioNova Smart HMS on this computer
# (Docker Desktop / Docker Engine with Compose v2). Phones on the same Wi-Fi
# can then open the web app and use the LAN demo APK. docs/DEMO.md.
#
#   scripts/demo-up.sh            start (first run builds images: ~5-10 min)
#   scripts/demo-up.sh down       stop, keep the demo data
#   scripts/demo-up.sh reset      stop and DELETE the demo data
#
# Never use this for real patients: it runs in development mode over plain
# HTTP, with throw-away secrets in infra/docker/.env.demo (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=infra/docker/.env.demo
COMPOSE=(docker compose -p hms-demo -f infra/docker/docker-compose.yml
         -f infra/docker/docker-compose.demo.yml --env-file "$ENV_FILE")

case "${1:-up}" in
  down) "${COMPOSE[@]}" down; exit 0 ;;
  reset) "${COMPOSE[@]}" down -v; rm -f "$ENV_FILE"; exit 0 ;;
  up) ;;
  *) echo "usage: $0 [up|down|reset]" >&2; exit 2 ;;
esac

command -v docker >/dev/null || { echo "Docker is not installed (docs/DEMO.md)." >&2; exit 1; }

if [ ! -f "$ENV_FILE" ]; then
  hex() { od -An -N24 -tx1 /dev/urandom | tr -d ' \n'; }
  key=$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n')
  umask 077
  cat > "$ENV_FILE" <<ENV
# Throw-away secrets for the synthetic-data demo (scripts/demo-up.sh).
HMS_PG_PASSWORD=$(hex)
HMS_APP_PASSWORD=$(hex)
JWT_SECRET=$(hex)
FIELD_ENCRYPTION_KEY=$key
HMS_ENVIRONMENT=development
HMS_BIND_ADDRESS=0.0.0.0
# Avoids clashing with a PostgreSQL already installed on this computer.
HMS_PG_HOST_PORT=55432
ENV
  echo "Created $ENV_FILE with random demo secrets."
fi

"${COMPOSE[@]}" up -d --build

echo "Waiting for the demo to start..."
for _ in $(seq 1 100); do
  if curl -sf http://127.0.0.1:3000/api/v1/health/ready >/dev/null 2>&1; then ready=1; break; fi
  sleep 3
done
if [ -z "${ready:-}" ]; then
  "${COMPOSE[@]}" ps -a
  echo "The demo did not become ready. Logs: ${COMPOSE[*]} logs" >&2
  exit 1
fi

ips=$( (hostname -I 2>/dev/null || ipconfig getifaddr en0 2>/dev/null || true) | tr ' ' '\n' \
       | grep -E '^(10|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.' || true)
echo
echo "Aditya BioNova Smart HMS demo is running (SYNTHETIC DATA ONLY)."
echo "  On this computer:   http://localhost:3000"
for ip in $ips; do
  echo "  From your phone:    http://$ip:3000   (web)"
  echo "  Android demo app:   server address $ip:8000"
done
[ -n "$ips" ] || echo "  (find this computer's Wi-Fi address and use http://<address>:3000)"
echo "  Password for every demo account: Demo-Sunrise-2026!   (accounts: docs/DEMO.md)"
