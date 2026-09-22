#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [ ! -f "$SECRETS_FILE" ]; then
  echo "Production secrets file not found: $SECRETS_FILE" >&2
  exit 1
fi

cd "$INSTALL_DIR"
chmod 600 "$SECRETS_FILE"
# shellcheck disable=SC1090
. "$SECRETS_FILE"

: "${XBOW_POSTGRES_PASSWORD:?missing XBOW_POSTGRES_PASSWORD}"
: "${XBOW_REDIS_PASSWORD:?missing XBOW_REDIS_PASSWORD}"
export XBOW_POSTGRES_PASSWORD XBOW_REDIS_PASSWORD
export XBOW_POSTGRES_DB="${XBOW_POSTGRES_DB:-xbow}"
export XBOW_POSTGRES_USER="${XBOW_POSTGRES_USER:-xbow}"
export XBOW_DATABASE_URL="postgresql://${XBOW_POSTGRES_USER}:${XBOW_POSTGRES_PASSWORD}@postgres:5432/${XBOW_POSTGRES_DB}"
export XBOW_REDIS_URL="redis://:${XBOW_REDIS_PASSWORD}@redis:6379/0"

COMPOSE=(
  docker compose
  -f docker-compose.yml
  -f docker-compose.distributed.yml
  -f docker-compose.tls.yml
)
"${COMPOSE[@]}" config --quiet

printf 'GitHub fine-grained token (repo Issues: Read and write): ' >&2
IFS= read -r -s TOKEN
printf '\n' >&2
if [ "${#TOKEN}" -lt 20 ]; then
  echo "Token too short; nothing changed." >&2
  exit 1
fi

printf '%s' "$TOKEN" | "${COMPOSE[@]}" exec -T backend python -c '
import sys
from app.secret_vault import set_secret, vault_enabled
from app.github_learning_sync import learning_sync_configuration
if not vault_enabled():
    raise SystemExit("vault is not enabled")
token = sys.stdin.read().strip()
if len(token) < 20:
    raise SystemExit("GitHub token is unexpectedly short")
set_secret("github_learning_token", token)
cfg = learning_sync_configuration()
if not cfg.get("configured"):
    raise SystemExit("GitHub learning token verification failed")
print("GitHub learning sync credential stored in vault")
print("repository:", cfg.get("repository"))
'
unset TOKEN
echo "Done. Completed batches will be summarized to GitHub automatically."
