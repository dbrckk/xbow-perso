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

# shellcheck disable=SC1090
. "$SECRETS_FILE"
export XBOW_POSTGRES_PASSWORD="${XBOW_POSTGRES_PASSWORD:-}"
export XBOW_REDIS_PASSWORD="${XBOW_REDIS_PASSWORD:-}"
export XBOW_POSTGRES_DB="${XBOW_POSTGRES_DB:-xbow}"
export XBOW_POSTGRES_USER="${XBOW_POSTGRES_USER:-xbow}"
export XBOW_DATABASE_URL="postgresql://${XBOW_POSTGRES_USER}:${XBOW_POSTGRES_PASSWORD}@postgres:5432/${XBOW_POSTGRES_DB}"
export XBOW_REDIS_URL="redis://:${XBOW_REDIS_PASSWORD}@redis:6379/0"

echo "=== SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps

echo "=== BACKEND READINESS ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness

echo "=== SAFE GATES ==="
for key in DRY_RUN XBOW_ENABLE_ACTIVE_SCANS XBOW_ENABLE_NUCLEI XBOW_ENABLE_HACKERONE_SUBMISSION; do
  value="$(grep -E "^[[:space:]]*${key}=" .env | tail -n1 | cut -d= -f2- || true)"
  printf '%s=%s\n' "$key" "$value"
done
