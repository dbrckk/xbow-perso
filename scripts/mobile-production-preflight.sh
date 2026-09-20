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

cd "$INSTALL_DIR"

read_env_value() {
  local key="$1"
  local value
  value="$(grep -E "^[[:space:]]*${key}=" .env | tail -n1 | cut -d= -f2- || true)"
  printf '%s' "$value"
}

require_gate() {
  local key="$1"
  local expected="$2"
  local actual
  actual="$(read_env_value "$key" | tr '[:upper:]' '[:lower:]')"
  if [ "$actual" != "$expected" ]; then
    echo "SAFE-GATE BLOCK: $key must be $expected before production migration preflight" >&2
    exit 1
  fi
}

require_gate "DRY_RUN" "true"
require_gate "XBOW_ENABLE_ACTIVE_SCANS" "false"
require_gate "XBOW_ENABLE_NUCLEI" "false"
require_gate "XBOW_ENABLE_HACKERONE_SUBMISSION" "false"

if [ ! -f "$SECRETS_FILE" ]; then
  install -m 600 /dev/null "$SECRETS_FILE"
  POSTGRES_PASSWORD="$(openssl rand -hex 32)"
  REDIS_PASSWORD="$(openssl rand -hex 32)"
  printf 'XBOW_POSTGRES_PASSWORD=%s\n' "$POSTGRES_PASSWORD" >> "$SECRETS_FILE"
  printf 'XBOW_REDIS_PASSWORD=%s\n' "$REDIS_PASSWORD" >> "$SECRETS_FILE"
else
  chmod 600 "$SECRETS_FILE"
fi

# shellcheck disable=SC1090
. "$SECRETS_FILE"

: "${XBOW_POSTGRES_PASSWORD:?missing XBOW_POSTGRES_PASSWORD in $SECRETS_FILE}"
: "${XBOW_REDIS_PASSWORD:?missing XBOW_REDIS_PASSWORD in $SECRETS_FILE}"

export XBOW_POSTGRES_PASSWORD
export XBOW_REDIS_PASSWORD
export XBOW_POSTGRES_DB="${XBOW_POSTGRES_DB:-xbow}"
export XBOW_POSTGRES_USER="${XBOW_POSTGRES_USER:-xbow}"
export XBOW_DATABASE_URL="postgresql://${XBOW_POSTGRES_USER}:${XBOW_POSTGRES_PASSWORD}@postgres:5432/${XBOW_POSTGRES_DB}"
export XBOW_REDIS_URL="redis://:${XBOW_REDIS_PASSWORD}@redis:6379/0"

echo "=== UPDATE ==="
git fetch --prune origin
git checkout main
git reset --hard origin/main

echo "=== COMPOSE VALIDATION ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml config --quiet

echo "=== START POSTGRES + REDIS ONLY ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml up -d postgres redis

echo "=== WAIT FOR DEPENDENCIES ==="
for _ in $(seq 1 45); do
  pg_ok="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps --format json postgres 2>/dev/null | grep -c '"Health":"healthy"' || true)"
  redis_ok="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps --format json redis 2>/dev/null | grep -c '"Health":"healthy"' || true)"
  if [ "$pg_ok" -gt 0 ] && [ "$redis_ok" -gt 0 ]; then
    break
  fi
  sleep 2
done

echo "=== DEPENDENCY STATUS ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps postgres redis

echo "=== MIGRATION PLAN ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml run --rm --no-deps   -e XBOW_MIGRATION_SQLITE_PATH=/data/xbow.sqlite3   -e XBOW_ARTIFACT_ROOT=/data/artifacts   -e XBOW_DATABASE_URL="$XBOW_DATABASE_URL"   -e XBOW_REDIS_URL="$XBOW_REDIS_URL"   backend python -m app.production_migration plan

echo "=== VAULT MIGRATION ==="
echo "Deferred: vault migration has a separate verified cutover step."

echo
echo "PRE-FLIGHT COMPLETE"
echo "No scanner service was started."
echo "Safe gates remain unchanged."
echo "Generated PostgreSQL/Redis credentials are stored only in $SECRETS_FILE (mode 600)."
echo "Do not share or screenshot that file."
