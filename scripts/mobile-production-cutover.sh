#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"
STATUS_FILE="${XBOW_MIGRATION_STATUS_FILE:-/root/xbow-storage-migration-status.json}"

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
  echo "Run scripts/mobile-production-preflight.sh first." >&2
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

echo "=== VALIDATE COMPOSE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml config --quiet

echo "=== START DATABASE SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml up -d postgres redis

echo "=== WAIT FOR DATABASE SERVICES ==="
for _ in $(seq 1 45); do
  pg_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps -q postgres)" 2>/dev/null || true)"
  redis_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps -q redis)" 2>/dev/null || true)"
  if [ "$pg_health" = "healthy" ] && [ "$redis_health" = "healthy" ]; then
    break
  fi
  sleep 2
done

pg_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps -q postgres)" 2>/dev/null || true)"
redis_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps -q redis)" 2>/dev/null || true)"
if [ "$pg_health" != "healthy" ] || [ "$redis_health" != "healthy" ]; then
  echo "Database services are not healthy; refusing cutover." >&2
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps postgres redis
  exit 1
fi

echo "=== FINAL READ-ONLY MIGRATION PLAN ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml run --rm --no-deps \
  -e XBOW_MIGRATION_SQLITE_PATH=/data/xbow.sqlite3 \
  -e XBOW_ARTIFACT_ROOT=/data/artifacts \
  -e XBOW_DATABASE_URL="$XBOW_DATABASE_URL" \
  -e XBOW_REDIS_URL="$XBOW_REDIS_URL" \
  backend python -m app.production_migration plan

echo "=== QUIESCE APPLICATION ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml stop \
  tls-proxy frontend worker backend || true

for profile_service in scanner-worker pentagi-worker pentagi-status-worker hackerone-report-sync-worker; do
  container_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps -q "$profile_service" 2>/dev/null || true)"
  if [ -n "$container_id" ]; then
    docker stop "$container_id" >/dev/null
  fi
done

echo "=== APPLY STORAGE MIGRATION ==="
set +e
migration_output="$(
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml run --rm --no-deps \
    -e XBOW_MIGRATION_QUIESCED=true \
    -e XBOW_MIGRATION_SQLITE_PATH=/data/xbow.sqlite3 \
    -e XBOW_ARTIFACT_ROOT=/data/artifacts \
    -e XBOW_DATABASE_URL="$XBOW_DATABASE_URL" \
    -e XBOW_REDIS_URL="$XBOW_REDIS_URL" \
    backend python -m app.production_migration apply 2>&1
)"
migration_rc=$?
set -e

printf '%s\n' "$migration_output"
if [ "$migration_rc" -ne 0 ]; then
  echo "Migration failed. Restarting the previous SQLite application stack." >&2
  docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build backend worker frontend tls-proxy
  exit "$migration_rc"
fi

printf '%s\n' "$migration_output" > "$STATUS_FILE"
chmod 600 "$STATUS_FILE"

echo "=== START DISTRIBUTED STACK ==="
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
  echo "Distributed backend failed health validation." >&2
  echo "Rollback command: sudo bash $INSTALL_DIR/scripts/mobile-production-rollback.sh" >&2
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
echo "STORAGE CUTOVER COMPLETE"
echo "SQLite source remains unchanged and a migration backup was created."
echo "Migration status saved to $STATUS_FILE (mode 600)."
echo "Safe scan/submission gates remain closed."
echo "Vault cutover has NOT been performed yet."
