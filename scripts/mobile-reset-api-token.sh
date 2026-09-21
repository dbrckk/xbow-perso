#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"

cd "$INSTALL_DIR"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

if [ ! -f "$SECRETS_FILE" ]; then
  echo "Production secrets file not found: $SECRETS_FILE" >&2
  exit 1
fi
chmod 600 "$SECRETS_FILE"

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

COMPOSE=(
  docker compose
  -f docker-compose.yml
  -f docker-compose.distributed.yml
  -f docker-compose.tls.yml
)

"${COMPOSE[@]}" config --quiet

TOKEN="$(openssl rand -hex 32)"
printf '%s' "$TOKEN" | "${COMPOSE[@]}" exec -T backend python -c '
import sys
from app.secret_vault import set_secret, vault_enabled
from app.auth import configured_api_token
if not vault_enabled():
    raise SystemExit("vault is not enabled")
token = sys.stdin.read().strip()
if len(token) < 32:
    raise SystemExit("generated token is unexpectedly short")
set_secret("api_token", token)
if configured_api_token() != token:
    raise SystemExit("vault api_token verification failed")
print("vault api_token updated and verified")
'

install -m 600 /dev/null /root/xbow-api-token.txt
printf '%s\n' "$TOKEN" > /root/xbow-api-token.txt

echo
echo "NEW XBOW API TOKEN:"
printf '%s\n' "$TOKEN"
echo
echo "Saved root-only at /root/xbow-api-token.txt"
echo "Paste this exact token into the dashboard Jeton API field."
