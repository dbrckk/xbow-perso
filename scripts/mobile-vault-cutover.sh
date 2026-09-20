#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"
STORAGE_STATUS_FILE="${XBOW_MIGRATION_STATUS_FILE:-/root/xbow-storage-migration-status.json}"
ENV_FILE="$INSTALL_DIR/.env"
BACKUP_FILE="$INSTALL_DIR/.env.pre-vault.bak"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [ ! -d "$INSTALL_DIR/.git" ] || [ ! -f "$ENV_FILE" ]; then
  echo "xbow-perso installation not found at $INSTALL_DIR" >&2
  exit 1
fi
if [ ! -f "$SECRETS_FILE" ]; then
  echo "Production secrets file not found: $SECRETS_FILE" >&2
  exit 1
fi
if [ ! -f "$STORAGE_STATUS_FILE" ]; then
  echo "Storage migration marker not found: $STORAGE_STATUS_FILE" >&2
  echo "Complete the PostgreSQL/Redis cutover first." >&2
  exit 1
fi
if [ -e "$BACKUP_FILE" ]; then
  echo "Vault env backup already exists: $BACKUP_FILE" >&2
  echo "Refusing a second vault rewrite until the previous backup is handled." >&2
  exit 1
fi

chmod 600 "$SECRETS_FILE" "$ENV_FILE"
cd "$INSTALL_DIR"

read_env_value() {
  local key="$1"
  grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true
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

echo "=== VERIFY DISTRIBUTED STORAGE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness

echo "=== VAULT MIGRATION PLAN ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml run --rm --no-deps \
  -e XBOW_VAULT_ENABLED=false \
  -e XBOW_VAULT_PATH=/data/secrets.vault.json \
  -e XBOW_VAULT_MASTER_KEY_FILE=/data/vault-master.key \
  -v "$ENV_FILE:/run/xbow-legacy.env:ro" \
  backend python -m app.vault_migration plan --source-env-file /run/xbow-legacy.env

echo "=== VAULT MIGRATION APPLY ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml run --rm --no-deps \
  -e XBOW_VAULT_ENABLED=false \
  -e XBOW_VAULT_PATH=/data/secrets.vault.json \
  -e XBOW_VAULT_MASTER_KEY_FILE=/data/vault-master.key \
  -v "$ENV_FILE:/run/xbow-legacy.env:ro" \
  backend python -m app.vault_migration apply --source-env-file /run/xbow-legacy.env

echo "=== VERIFY REQUIRED VAULT AUTH SECRET ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml run --rm --no-deps \
  -e XBOW_VAULT_ENABLED=true \
  -e XBOW_VAULT_PATH=/data/secrets.vault.json \
  -e XBOW_VAULT_MASTER_KEY_FILE=/data/vault-master.key \
  -e XBOW_API_TOKEN= \
  -e XBOW_API_TOKEN_FILE= \
  backend python -c 'from app.auth import configured_api_token; configured_api_token(); print("api-auth=ok")'

h1_present=false
if grep -Eq '^[[:space:]]*XBOW_HACKERONE_API_USERNAME=.+$' "$ENV_FILE" \
   && grep -Eq '^[[:space:]]*XBOW_HACKERONE_API_TOKEN=.+$' "$ENV_FILE"; then
  h1_present=true
fi

if [ "$h1_present" = "true" ]; then
  echo "=== VERIFY HACKERONE VAULT CREDENTIALS ==="
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml run --rm --no-deps \
    -e XBOW_VAULT_ENABLED=true \
    -e XBOW_VAULT_PATH=/data/secrets.vault.json \
    -e XBOW_VAULT_MASTER_KEY_FILE=/data/vault-master.key \
    -e XBOW_HACKERONE_API_USERNAME= \
    -e XBOW_HACKERONE_API_TOKEN= \
    backend python -c 'from app.hackerone_client import load_hackerone_credentials; load_hackerone_credentials(); print("hackerone-credentials=ok")'
fi

echo "=== BACKUP AND REWRITE HOST ENV ==="
python3 - "$ENV_FILE" "$BACKUP_FILE" <<'PY'
from pathlib import Path
import os
import sys

env_path = Path(sys.argv[1])
backup_path = Path(sys.argv[2])
original = env_path.read_text(encoding="utf-8")
backup_path.write_text(original, encoding="utf-8")
os.chmod(backup_path, 0o600)

remove_exact = {
    "XBOW_API_TOKEN",
    "XBOW_API_TOKEN_FILE",
    "XBOW_HACKERONE_API_USERNAME",
    "XBOW_HACKERONE_API_TOKEN",
    "XBOW_PENTAGI_API_TOKEN",
    "LLM_API_KEY",
    "PERPLEXITY_API_KEY",
    "XBOW_AUDIT_HMAC_KEY",
    "XBOW_TOTP_SECRET",
    "XBOW_ALERT_WEBHOOK_HMAC_KEY",
    "XBOW_VAULT_ENABLED",
    "XBOW_VAULT_MASTER_KEY",
    "XBOW_VAULT_MASTER_KEY_FILE",
}
out = []
for line in original.splitlines():
    stripped = line.strip()
    candidate = stripped.removeprefix("export ").lstrip()
    if "=" in candidate and not candidate.startswith("#"):
        name = candidate.split("=", 1)[0].strip()
        if name in remove_exact or name.startswith("XBOW_BROWSER_SECRET_"):
            continue
    out.append(line)
out.extend([
    "XBOW_VAULT_ENABLED=true",
    "XBOW_VAULT_PATH=/data/secrets.vault.json",
    "XBOW_VAULT_MASTER_KEY_FILE=/data/vault-master.key",
])
tmp = env_path.with_name(env_path.name + ".vault-cutover.tmp")
tmp.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
os.replace(tmp, env_path)
os.chmod(env_path, 0o600)
PY

rollback_and_exit() {
  local reason="$1"
  echo "$reason" >&2
  echo "Restoring pre-vault environment and distributed stack." >&2
  cp "$BACKUP_FILE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml up -d --build \
    postgres redis backend worker frontend tls-proxy || true
  exit 1
}

echo "=== RESTART DISTRIBUTED STACK WITH VAULT ==="
set +e
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml up -d --build \
  postgres redis backend worker frontend tls-proxy
restart_rc=$?
set -e
if [ "$restart_rc" -ne 0 ]; then
  rollback_and_exit "Vault-enabled restart failed."
fi

echo "=== WAIT FOR BACKEND ==="
for _ in $(seq 1 60); do
  backend_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q backend 2>/dev/null || true)"
  backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
  if [ "$backend_health" = "healthy" ]; then
    break
  fi
  sleep 2
done

backend_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q backend 2>/dev/null || true)"
backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
if [ "$backend_health" != "healthy" ]; then
  rollback_and_exit "Vault-enabled backend failed health validation."
fi

echo "=== VAULT RUNTIME VERIFICATION ==="
if ! docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend \
  python -c 'from app.auth import configured_api_token; configured_api_token(); print("api-auth=ok")'; then
  rollback_and_exit "Vault-backed API authentication verification failed."
fi

if ! docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend \
  python -m app.readiness; then
  rollback_and_exit "Backend readiness failed after vault cutover."
fi

PUBLIC_HOST="$(read_env_value XBOW_PUBLIC_HOST)"
if [ -n "$PUBLIC_HOST" ]; then
  echo "=== HTTPS ==="
  if ! curl -fsSI "https://$PUBLIC_HOST" | sed -n '1,12p'; then
    rollback_and_exit "HTTPS validation failed after vault cutover."
  fi
fi

echo
echo "VAULT CUTOVER COMPLETE"
echo "Encrypted vault is enabled with a file-backed master key."
echo "Legacy secret assignments were removed from .env after verification."
echo "Backup retained at $BACKUP_FILE (mode 600)."
echo "Safe scan/submission gates remain closed."
