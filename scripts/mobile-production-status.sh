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

echo "=== DEPLOYED REVISION ==="
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git ls-remote origin refs/heads/main 2>/dev/null | awk '{print $1}' | head -n1 || true)"
echo "LOCAL_SHA=$LOCAL_SHA"
echo "ORIGIN_MAIN_SHA=$REMOTE_SHA"
REMOTE_MAIN_REACHABLE=false
CHECKOUT_CURRENT=false
if [ -n "$REMOTE_SHA" ]; then
  REMOTE_MAIN_REACHABLE=true
  if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
    CHECKOUT_CURRENT=true
  fi
fi
echo "REMOTE_MAIN_REACHABLE=$REMOTE_MAIN_REACHABLE"
echo "CHECKOUT_CURRENT=$CHECKOUT_CURRENT"


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
  if curl -fsS -D - -o /dev/null "https://$PUBLIC_HOST/health" | sed -n '1,12p'; then
    PUBLIC_HTTPS_OK=true
    echo "PUBLIC_HTTPS_OK=true"
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

DASHBOARD_VERSION_OK=false
EXPECTED_DASHBOARD_ASSET="$(
  grep -o 'simple.js?v=[0-9][0-9]*' frontend/index.html \
    | head -n1 \
    || true
)"
if [ -n "$PUBLIC_HOST" ]; then
  echo "=== DASHBOARD ASSET VERSION ==="
  DASHBOARD_ASSET="$(
    curl -fsS "https://$PUBLIC_HOST/" \
      | grep -o 'simple.js?v=[0-9][0-9]*' \
      | head -n1 \
      || true
  )"
  echo "EXPECTED_DASHBOARD_ASSET=$EXPECTED_DASHBOARD_ASSET"
  echo "PUBLIC_DASHBOARD_ASSET=$DASHBOARD_ASSET"
  if [ -n "$EXPECTED_DASHBOARD_ASSET" ] \
    && [ "$DASHBOARD_ASSET" = "$EXPECTED_DASHBOARD_ASSET" ]; then
    DASHBOARD_VERSION_OK=true
  fi
  echo "DASHBOARD_VERSION_OK=$DASHBOARD_VERSION_OK"
fi

echo "=== APPLICATION ROUTE CONTRACT ==="
if docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner exec -T backend python - <<'PY'
from app.main import app

paths = {
    str(path)
    for route in app.routes
    if (path := getattr(route, "path", None))
}
required = {
    "/api/hackerone/simple-review-package",
    "/api/imports/hackerone/rules-preview",
    "/api/imports/hackerone/batches/launch-reviewed",
    "/api/hackerone/journal",
    "/api/labs/htb/campaigns",
    "/api/labs/htb/campaigns/{campaign_id}/outcome",
    "/api/labs/htb/campaigns/{campaign_id}/learning",
    "/api/labs/htb/campaigns/{campaign_id}/status",
    "/api/labs/htb/learning",
    "/api/labs/htb/benchmark",
}
missing = sorted(required - paths)
print("APP_ROUTE_CONTRACT_OK=" + ("true" if not missing else "false"))
for path in missing:
    print("MISSING_ROUTE=" + path)
raise SystemExit(0 if not missing else 1)
PY
then
  APP_ROUTE_CONTRACT_OK=true
else
  APP_ROUTE_CONTRACT_OK=false
fi

echo "=== ACCESSIBLE BOUNTY PRECHECK ==="
ACCESSIBLE_BOUNTY_PRECHECK_OK=false
ACCESSIBLE_BOUNTY_RESULT="$(
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml --profile scanner exec -T backend python - <<'PY'
from app.hackerone_api import hackerone_simple_review_package
from fastapi import HTTPException

try:
    result = hackerone_simple_review_package()
except HTTPException as exc:
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    print("ACCESSIBLE_BOUNTY_PRECHECK_OK=false")
    print("ACCESSIBLE_BOUNTY_REASON=" + str(detail.get("reason") or "http_error"))
    print("ACCESSIBLE_BOUNTY_MESSAGE=" + str(detail.get("message") or "precheck failed"))
    raise SystemExit(1)
except Exception as exc:
    print("ACCESSIBLE_BOUNTY_PRECHECK_OK=false")
    print("ACCESSIBLE_BOUNTY_REASON=unexpected_error")
    print("ACCESSIBLE_BOUNTY_MESSAGE=" + exc.__class__.__name__)
    raise SystemExit(1)

handles = [str(value) for value in list(result.get("handles") or []) if str(value)]
ok = 1 <= len(handles) <= 2 and result.get("live_verified") is True
print("ACCESSIBLE_BOUNTY_PRECHECK_OK=" + ("true" if ok else "false"))
print("ACCESSIBLE_BOUNTY_COUNT=" + str(len(handles)))
print("ACCESSIBLE_BOUNTY_HANDLES=" + ",".join(handles))
print("ACCESSIBLE_BOUNTY_REVIEW_COUNT=" + str(int(result.get("review_count") or 0)))
print("ACCESSIBLE_BOUNTY_READY_COUNT=" + str(int(result.get("ready_count") or 0)))
raise SystemExit(0 if ok else 1)
PY
)" || true
printf '%s
' "$ACCESSIBLE_BOUNTY_RESULT"
if printf '%s
' "$ACCESSIBLE_BOUNTY_RESULT" | grep -qx 'ACCESSIBLE_BOUNTY_PRECHECK_OK=true'; then
  ACCESSIBLE_BOUNTY_PRECHECK_OK=true
fi

echo "=== PRODUCTION CONTRACT VERDICT ==="
if [ "$RUNTIME_READY" = "true" ] \
  && [ "$PUBLIC_HTTPS_OK" = "true" ] \
  && [ "$HACKERONE_API_READY" = "true" ] \
  && [ "$DASHBOARD_VERSION_OK" = "true" ] \
  && [ "$APP_ROUTE_CONTRACT_OK" = "true" ] \
  && [ "$ACCESSIBLE_BOUNTY_PRECHECK_OK" = "true" ] \
  && [ "$REMOTE_MAIN_REACHABLE" = "true" ] \
  && [ "$CHECKOUT_CURRENT" = "true" ]; then
  echo "PRODUCTION_CONTRACT_OK=true"
else
  echo "PRODUCTION_CONTRACT_OK=false"
  [ "$REMOTE_MAIN_REACHABLE" = "true" ] || echo "BLOCKER=origin_main_unreachable | Impossible de lire origin/main depuis le VPS."
  [ "$CHECKOUT_CURRENT" = "true" ] || echo "BLOCKER=checkout_stale | Le VPS n'est pas sur origin/main."
  [ "$DASHBOARD_VERSION_OK" = "true" ] || echo "BLOCKER=dashboard_version | Le dashboard public ne correspond pas au frontend du checkout déployé."
  [ "$APP_ROUTE_CONTRACT_OK" = "true" ] || echo "BLOCKER=route_contract | Une route critique de l'application manque dans le backend déployé."
  [ "$ACCESSIBLE_BOUNTY_PRECHECK_OK" = "true" ] || echo "BLOCKER=accessible_bounty_precheck | Aucun programme HackerOne live-vérifié n'a pu être préparé."
  exit 1
fi
