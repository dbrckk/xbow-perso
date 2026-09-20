#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

if [ ! -d "$INSTALL_DIR/.git" ] || [ ! -f "$INSTALL_DIR/.env" ]; then
  echo "xbow-perso installation not found at $INSTALL_DIR" >&2
  exit 1
fi
if [ ! -f "$SECRETS_FILE" ]; then
  echo "Production secrets file not found: $SECRETS_FILE" >&2
  exit 1
fi
chmod 600 "$SECRETS_FILE"

cd "$INSTALL_DIR"

read_env_value() {
  local key="$1"
  grep -E "^[[:space:]]*${key}=" .env | tail -n1 | cut -d= -f2- || true
}

require_gate() {
  local key="$1"
  local expected="$2"
  local actual
  actual="$(read_env_value "$key" | tr '[:upper:]' '[:lower:]')"
  if [ "$actual" != "$expected" ]; then
    echo "SAFE-GATE BLOCK: $key must be $expected" >&2
    exit 1
  fi
}

require_gate "DRY_RUN" "true"
require_gate "XBOW_ENABLE_ACTIVE_SCANS" "false"
require_gate "XBOW_ENABLE_NUCLEI" "false"
require_gate "XBOW_ENABLE_HACKERONE_SUBMISSION" "false"

# shellcheck disable=SC1090
. "$SECRETS_FILE"
: "${XBOW_POSTGRES_PASSWORD:?missing XBOW_POSTGRES_PASSWORD}"
: "${XBOW_REDIS_PASSWORD:?missing XBOW_REDIS_PASSWORD}"

export XBOW_POSTGRES_PASSWORD
export XBOW_REDIS_PASSWORD
export XBOW_POSTGRES_DB="${XBOW_POSTGRES_DB:-xbow}"
export XBOW_POSTGRES_USER="${XBOW_POSTGRES_USER:-xbow}"
export XBOW_DATABASE_URL="postgresql://${XBOW_POSTGRES_USER}:${XBOW_POSTGRES_PASSWORD}@postgres:5432/${XBOW_POSTGRES_DB}"
export XBOW_REDIS_URL="redis://:${XBOW_REDIS_PASSWORD}@redis:6379/0"

echo "=== UPDATE MAIN ==="
git fetch --prune origin
git checkout main
git reset --hard origin/main

echo "=== VALIDATE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml config --quiet

echo "=== DEPLOY SAFE PRODUCTION SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml up -d --build \
  postgres redis backend worker frontend tls-proxy

echo "=== WAIT FOR BACKEND ==="
for _ in $(seq 1 60); do
  backend_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q backend 2>/dev/null || true)"
  backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
  if [ "$backend_health" = "healthy" ]; then
    break
  fi
  sleep 2
done

backend_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q backend)"
backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
if [ "$backend_health" != "healthy" ]; then
  echo "Backend failed health validation." >&2
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps
  exit 1
fi

echo "=== READINESS ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness

echo "=== SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps

PUBLIC_HOST="$(read_env_value XBOW_PUBLIC_HOST)"
if [ -n "$PUBLIC_HOST" ]; then
  echo "=== HTTPS ==="
  curl -fsSI "https://$PUBLIC_HOST" | sed -n '1,12p'
fi

echo
echo "SAFE PRODUCTION UPDATE COMPLETE"
echo "No scanner, PentAGI, or HackerOne submission profile was started."
