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
require_gate "XBOW_ENABLE_RECON" "false"
require_gate "XBOW_ENABLE_EXTERNAL_RECON" "false"
require_gate "XBOW_ENABLE_BROWSER_AUTOMATION" "false"
require_gate "XBOW_ENABLE_HACKERONE_SUBMISSION" "false"

if [ -f "$SECRETS_FILE" ]; then
  chmod 600 "$SECRETS_FILE"
  # shellcheck disable=SC1090
  . "$SECRETS_FILE"
  export XBOW_POSTGRES_PASSWORD="${XBOW_POSTGRES_PASSWORD:-}"
  export XBOW_REDIS_PASSWORD="${XBOW_REDIS_PASSWORD:-}"
  export XBOW_DATABASE_URL="${XBOW_DATABASE_URL:-postgresql://${XBOW_POSTGRES_USER:-xbow}:${XBOW_POSTGRES_PASSWORD:-}@postgres:5432/${XBOW_POSTGRES_DB:-xbow}}"
  export XBOW_REDIS_URL="${XBOW_REDIS_URL:-redis://:${XBOW_REDIS_PASSWORD:-}@redis:6379/0}"
fi

echo "=== STOP DISTRIBUTED APPLICATION SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml stop \
  tls-proxy frontend worker backend || true

for profile_service in scanner-worker pentagi-worker pentagi-status-worker hackerone-report-sync-worker; do
  container_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml ps -q "$profile_service" 2>/dev/null || true)"
  if [ -n "$container_id" ]; then
    docker stop "$container_id" >/dev/null
  fi
done

echo "=== RESTART SQLITE STACK ==="
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build backend worker frontend tls-proxy

echo "=== WAIT FOR SQLITE BACKEND ==="
for _ in $(seq 1 60); do
  backend_id="$(docker compose -f docker-compose.yml -f docker-compose.tls.yml ps -q backend 2>/dev/null || true)"
  backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
  if [ "$backend_health" = "healthy" ]; then
    break
  fi
  sleep 2
done

backend_id="$(docker compose -f docker-compose.yml -f docker-compose.tls.yml ps -q backend)"
backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
if [ "$backend_health" != "healthy" ]; then
  echo "SQLite rollback stack is not healthy." >&2
  docker compose -f docker-compose.yml -f docker-compose.tls.yml ps
  exit 1
fi

docker compose -f docker-compose.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness

echo
echo "ROLLBACK COMPLETE"
echo "Application services are using the original SQLite backend again."
echo "PostgreSQL/Redis data were not deleted."
echo "Safe scan/submission gates remain closed."
