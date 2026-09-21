#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"
LIVE_PROFILE_FILE="${XBOW_LIVE_SCANNER_PROFILE_FILE:-/root/xbow-live-scanner.env}"

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

REPO_OWNER="$(stat -c '%U' "$INSTALL_DIR")"
if [ -z "$REPO_OWNER" ] || [ "$REPO_OWNER" = "UNKNOWN" ]; then
  echo "Unable to determine repository owner for safe Git update." >&2
  exit 1
fi

git_as_owner() {
  if [ "$REPO_OWNER" = "root" ]; then
    git -C "$INSTALL_DIR" "$@"
  else
    runuser -u "$REPO_OWNER" -- git -C "$INSTALL_DIR" "$@"
  fi
}

read_env_value() {
  local key="$1"
  grep -E "^[[:space:]]*${key}=" .env | tail -n1 | cut -d= -f2- || true
}

require_baseline_gate() {
  local key="$1"
  local expected="$2"
  local actual
  actual="$(read_env_value "$key" | tr '[:upper:]' '[:lower:]')"
  if [ "$actual" != "$expected" ]; then
    echo "SAFE-BASELINE BLOCK: $key in .env must remain $expected" >&2
    exit 1
  fi
}

require_live_value() {
  local key="$1"
  local expected="$2"
  local actual="${!key-}"
  if [ "$actual" != "$expected" ]; then
    echo "LIVE-PROFILE BLOCK: $key must be $expected" >&2
    exit 1
  fi
}

# The repository .env remains fail-safe even when the root-only live overlay is armed.
require_baseline_gate "DRY_RUN" "true"
require_baseline_gate "XBOW_ENABLE_ACTIVE_SCANS" "false"
require_baseline_gate "XBOW_ENABLE_NUCLEI" "false"
require_baseline_gate "XBOW_ENABLE_RECON" "false"
require_baseline_gate "XBOW_ENABLE_EXTERNAL_RECON" "false"
require_baseline_gate "XBOW_ENABLE_BROWSER_AUTOMATION" "false"
require_baseline_gate "XBOW_ENABLE_HACKERONE_SUBMISSION" "false"

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

LIVE_MODE=false
if [ -f "$LIVE_PROFILE_FILE" ]; then
  chmod 600 "$LIVE_PROFILE_FILE"
  # shellcheck disable=SC1090
  . "$LIVE_PROFILE_FILE"
  require_live_value "DRY_RUN" "false"
  require_live_value "XBOW_ENABLE_ACTIVE_SCANS" "true"
  require_live_value "XBOW_ENABLE_SCANNER_WORKER" "true"
  require_live_value "XBOW_ENABLE_NUCLEI" "true"
  require_live_value "XBOW_ENABLE_RECON" "true"
  require_live_value "XBOW_ENABLE_EXTERNAL_RECON" "false"
  require_live_value "XBOW_ENABLE_BROWSER_AUTOMATION" "false"
  require_live_value "XBOW_SCAN_ENGINES" "nuclei"
  require_live_value "XBOW_SCANNER_ALLOWED_ENGINES" "nuclei"
  require_live_value "XBOW_SCANNER_SANDBOX_PROFILE" "restricted-v1"
  require_live_value "XBOW_NUCLEI_ALLOWED_VERSION" "3.11.1"
  require_live_value "XBOW_ENABLE_HACKERONE_SUBMISSION" "false"

  export DRY_RUN XBOW_ENABLE_ACTIVE_SCANS XBOW_ENABLE_SCANNER_WORKER
  export XBOW_ENABLE_NUCLEI XBOW_ENABLE_RECON XBOW_ENABLE_EXTERNAL_RECON
  export XBOW_ENABLE_BROWSER_AUTOMATION XBOW_SCAN_ENGINES XBOW_SCANNER_ALLOWED_ENGINES
  export XBOW_SCANNER_SANDBOX_PROFILE XBOW_NUCLEI_ALLOWED_VERSION
  export XBOW_ENABLE_HACKERONE_SUBMISSION
  export XBOW_MAX_AUTONOMOUS_RPS="${XBOW_MAX_AUTONOMOUS_RPS:-2.0}"
  LIVE_MODE=true
else
  export DRY_RUN=true
  export XBOW_ENABLE_ACTIVE_SCANS=false
  export XBOW_ENABLE_SCANNER_WORKER=false
  export XBOW_ENABLE_NUCLEI=false
  export XBOW_ENABLE_RECON=false
  export XBOW_ENABLE_EXTERNAL_RECON=false
  export XBOW_ENABLE_BROWSER_AUTOMATION=false
  export XBOW_SCAN_ENGINES=nuclei
  export XBOW_SCANNER_ALLOWED_ENGINES=nuclei
  export XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1
  export XBOW_ENABLE_HACKERONE_SUBMISSION=false
  unset XBOW_NUCLEI_ALLOWED_VERSION || true
fi

echo "=== UPDATE MAIN ==="
git_as_owner fetch --prune origin
git_as_owner checkout main
git_as_owner reset --hard origin/main

COMPOSE=(
  docker compose
  -f docker-compose.yml
  -f docker-compose.distributed.yml
  -f docker-compose.tls.yml
)
if [ "$LIVE_MODE" = "true" ]; then
  COMPOSE+=(--profile scanner)
fi

echo "=== VALIDATE ==="
"${COMPOSE[@]}" config --quiet

if [ "$LIVE_MODE" = "true" ]; then
  echo "=== DEPLOY PRODUCTION + PERSISTENT NUCLEI PROFILE ==="
  "${COMPOSE[@]}" up -d --build \
    postgres redis backend worker scanner-worker frontend tls-proxy
else
  echo "=== DEPLOY SAFE PRODUCTION SERVICES ==="
  "${COMPOSE[@]}" up -d --build \
    postgres redis backend worker frontend tls-proxy
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.distributed.yml \
    -f docker-compose.tls.yml \
    --profile scanner rm -sf scanner-worker >/dev/null 2>&1 || true
fi

echo "=== WAIT FOR BACKEND ==="
for _ in $(seq 1 60); do
  backend_id="$("${COMPOSE[@]}" ps -q backend 2>/dev/null || true)"
  backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
  if [ "$backend_health" = "healthy" ]; then
    break
  fi
  sleep 2
done

backend_id="$("${COMPOSE[@]}" ps -q backend)"
backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
if [ "$backend_health" != "healthy" ]; then
  echo "Backend failed health validation." >&2
  "${COMPOSE[@]}" ps
  exit 1
fi

echo "=== READINESS ==="
"${COMPOSE[@]}" exec -T backend python -m app.readiness

if [ "$LIVE_MODE" = "true" ]; then
  echo "=== SCANNER CAPABILITY ==="
  "${COMPOSE[@]}" exec -T backend python -c \
    'from app.runtime_capabilities import scanner_runtime_capability; c=scanner_runtime_capability(); assert c["dispatch_ready"] and c["nuclei_enabled"] and c["nuclei_execution_intent"], c; print(c)'

  echo "=== RECON CAPABILITY ==="
  "${COMPOSE[@]}" exec -T backend python -c \
    'from app.runtime_capabilities import recon_runtime_capability; c=recon_runtime_capability(); assert c["dispatch_ready"] and c["recon_enabled"] and not c["external_recon_enabled"], c; print(c)'

  echo "=== SCANNER SANDBOX ATTESTATION ==="
  "${COMPOSE[@]}" exec -T scanner-worker python -c \
    'from app.scanner_sandbox import require_scanner_sandbox; print(require_scanner_sandbox("nuclei").to_dict())'

  echo "=== NUCLEI VERSION ==="
  "${COMPOSE[@]}" exec -T scanner-worker sh -c \
    'nuclei -version 2>&1 | grep -F "$XBOW_NUCLEI_ALLOWED_VERSION"'
fi

echo "=== SERVICES ==="
"${COMPOSE[@]}" ps

PUBLIC_HOST="$(read_env_value XBOW_PUBLIC_HOST)"
if [ -n "$PUBLIC_HOST" ]; then
  echo "=== HTTPS ==="
  curl -fsSI "https://$PUBLIC_HOST" | sed -n '1,12p'
fi

echo
if [ "$LIVE_MODE" = "true" ]; then
  echo "PRODUCTION UPDATE COMPLETE — PERSISTENT NUCLEI PROFILE ARMED"
  echo "Per-program scope/policy/fingerprint gates remain mandatory."
  echo "HackerOne report submission remains disabled."
else
  echo "SAFE PRODUCTION UPDATE COMPLETE"
  echo "No active scanner profile is armed."
fi
