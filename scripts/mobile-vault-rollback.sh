#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"
ENV_FILE="$INSTALL_DIR/.env"
BACKUP_FILE="$INSTALL_DIR/.env.pre-vault.bak"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [ ! -f "$BACKUP_FILE" ] || [ ! -f "$SECRETS_FILE" ]; then
  echo "Vault rollback prerequisites are missing." >&2
  exit 1
fi

cd "$INSTALL_DIR"
chmod 600 "$SECRETS_FILE" "$BACKUP_FILE"

# shellcheck disable=SC1090
. "$SECRETS_FILE"
# XBOW_API_TOKEN_FILE auth-source normalization
# When vault is active, legacy API-token env/file sources must not leak into
# the backend. Without vault, secrets loaded from the root-only secrets file
# must be exported so docker compose receives the same token the operator uses.
auth_vault_mode="$(read_env_value XBOW_VAULT_ENABLED | tr '[:upper:]' '[:lower:]')"
case "$auth_vault_mode" in
  true|1|yes|on)
    unset XBOW_API_TOKEN XBOW_API_TOKEN_FILE || true
    ;;
  *)
    if [ -n "${XBOW_API_TOKEN-}" ]; then
      export XBOW_API_TOKEN
    fi
    if [ -n "${XBOW_API_TOKEN_FILE-}" ]; then
      export XBOW_API_TOKEN_FILE
    fi
    ;;
esac
: "${XBOW_POSTGRES_PASSWORD:?missing XBOW_POSTGRES_PASSWORD}"
: "${XBOW_REDIS_PASSWORD:?missing XBOW_REDIS_PASSWORD}"
export XBOW_POSTGRES_PASSWORD
export XBOW_REDIS_PASSWORD
export XBOW_POSTGRES_DB="${XBOW_POSTGRES_DB:-xbow}"
export XBOW_POSTGRES_USER="${XBOW_POSTGRES_USER:-xbow}"
export XBOW_DATABASE_URL="postgresql://${XBOW_POSTGRES_USER}:${XBOW_POSTGRES_PASSWORD}@postgres:5432/${XBOW_POSTGRES_DB}"
export XBOW_REDIS_URL="redis://:${XBOW_REDIS_PASSWORD}@redis:6379/0"

cp "$BACKUP_FILE" "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "=== RESTART DISTRIBUTED STACK WITH LEGACY SECRET SOURCES ==="
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

docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness

echo
echo "VAULT ROLLBACK COMPLETE"
echo "The pre-vault .env has been restored."
echo "The encrypted vault files were preserved for diagnosis/retry."
