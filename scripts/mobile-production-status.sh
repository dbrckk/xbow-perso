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

# shellcheck disable=SC1090
. "$SECRETS_FILE"
export XBOW_POSTGRES_PASSWORD="${XBOW_POSTGRES_PASSWORD:-}"
export XBOW_REDIS_PASSWORD="${XBOW_REDIS_PASSWORD:-}"
export XBOW_POSTGRES_DB="${XBOW_POSTGRES_DB:-xbow}"
export XBOW_POSTGRES_USER="${XBOW_POSTGRES_USER:-xbow}"
export XBOW_DATABASE_URL="postgresql://${XBOW_POSTGRES_USER}:${XBOW_POSTGRES_PASSWORD}@postgres:5432/${XBOW_POSTGRES_DB}"
export XBOW_REDIS_URL="redis://:${XBOW_REDIS_PASSWORD}@redis:6379/0"

LIVE_MODE=false
if [ -f "$LIVE_PROFILE_FILE" ]; then
  chmod 600 "$LIVE_PROFILE_FILE"
  # shellcheck disable=SC1090
  . "$LIVE_PROFILE_FILE"
  export DRY_RUN XBOW_ENABLE_ACTIVE_SCANS XBOW_ENABLE_SCANNER_WORKER
  export XBOW_ENABLE_NUCLEI XBOW_SCAN_ENGINES XBOW_SCANNER_ALLOWED_ENGINES
  export XBOW_SCANNER_SANDBOX_PROFILE XBOW_NUCLEI_ALLOWED_VERSION
  export XBOW_ENABLE_HACKERONE_SUBMISSION
  LIVE_MODE=true
fi

echo "=== SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps

echo "=== BACKEND READINESS ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness

echo "=== BASELINE GATES (.env) ==="
for key in DRY_RUN XBOW_ENABLE_ACTIVE_SCANS XBOW_ENABLE_NUCLEI XBOW_ENABLE_HACKERONE_SUBMISSION; do
  value="$(grep -E "^[[:space:]]*${key}=" .env | tail -n1 | cut -d= -f2- || true)"
  printf '%s=%s\n' "$key" "$value"
done

echo "=== PERSISTENT SCANNER PROFILE ==="
if [ "$LIVE_MODE" = "true" ]; then
  echo "armed=true"
  echo "engine=nuclei"
  echo "submission=false"
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner ps scanner-worker
  echo "=== SCANNER CAPABILITY ==="
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner exec -T backend python -c \
    'from app.runtime_capabilities import scanner_runtime_capability; print(scanner_runtime_capability())'
  echo "=== WORKER LIVENESS ==="
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner exec -T backend python -c \
    'from app.worker_liveness import worker_liveness_snapshot; print(worker_liveness_snapshot())'
  echo "=== HACKERONE LIVE READINESS ==="
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner exec -T backend python -c \
    'from app.hackerone_live_readiness import build_hackerone_live_readiness; from app.main import dependency_readiness; r=build_hackerone_live_readiness(dependency_readiness()); print({"status": r["status"], "live_scan_ready": r["live_scan_ready"], "failed": [x["id"] for x in r["checks"] if x["required"] and not x["ok"]]})'
else
  echo "armed=false"
  echo "HACKERONE_LIVE_READY=false"
fi

PUBLIC_HOST="$(grep -E '^[[:space:]]*XBOW_PUBLIC_HOST=' .env | tail -n1 | cut -d= -f2- || true)"
PUBLIC_HTTPS_OK=false
if [ -n "$PUBLIC_HOST" ]; then
  echo "=== PUBLIC HTTPS ==="
  if curl -fsSI "https://$PUBLIC_HOST/health" | sed -n '1,12p'; then
    PUBLIC_HTTPS_OK=true
  else
    echo "PUBLIC_HTTPS_OK=false"
  fi
fi

echo "=== HACKERONE API PROBE ==="
HACKERONE_API_READY=false
if docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner exec -T backend python - <<'PY'
from app.hackerone_client import HackerOneClient, HackerOneClientError, load_hackerone_credentials

try:
    credentials = load_hackerone_credentials()
    HackerOneClient(credentials).get_json(
        "hackers/programs",
        {"page[number]": 1, "page[size]": 1},
    )
except HackerOneClientError:
    print("HACKERONE_API_READY=false")
    raise SystemExit(1)
print("HACKERONE_API_READY=true")
PY
then
  HACKERONE_API_READY=true
fi

echo "=== BUG BOUNTY LAUNCH VERDICT ==="
RUNTIME_RESULT="$(
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner exec -T backend python - <<'PY'
from app.hackerone_live_readiness import build_hackerone_live_readiness
from app.main import dependency_readiness

result = build_hackerone_live_readiness(dependency_readiness())
failed = [
    {
        "id": item.get("id"),
        "label": item.get("label"),
        "action": item.get("action"),
    }
    for item in result.get("checks", [])
    if item.get("required") is True and item.get("ok") is not True
]
print("RUNTIME_READY=" + ("true" if result.get("live_scan_ready") is True else "false"))
for item in failed:
    print(f"BLOCKER={item['id']} | {item['label']} | {item['action']}")
PY
)"
printf '%s\n' "$RUNTIME_RESULT"
RUNTIME_READY="$(printf '%s\n' "$RUNTIME_RESULT" | sed -n 's/^RUNTIME_READY=//p' | head -n1)"
if [ "$RUNTIME_READY" = "true" ] && [ "$PUBLIC_HTTPS_OK" = "true" ] && [ "$HACKERONE_API_READY" = "true" ]; then
  echo "BUG_BOUNTY_LAUNCH_READY=true"
  echo "VERDICT=READY"
else
  echo "BUG_BOUNTY_LAUNCH_READY=false"
  echo "VERDICT=BLOCKED"
  if [ "$PUBLIC_HTTPS_OK" != "true" ]; then
    echo "BLOCKER=public_https | Dashboard HTTPS public inaccessible | Vérifier tls-proxy, DNS/sslip.io et les ports 80/443."
  fi
  if [ "$HACKERONE_API_READY" != "true" ]; then
    echo "BLOCKER=hackerone_api | API HackerOne inaccessible ou authentification refusée | Vérifier le réseau VPS et les credentials HackerOne."
  fi
fi

if [ -n "$PUBLIC_HOST" ]; then
  echo "=== DASHBOARD ASSET VERSION ==="
  curl -fsS "https://$PUBLIC_HOST/" \
    | grep -o 'simple.js?v=[0-9][0-9]*' \
    | head -n1 \
    || true
fi
