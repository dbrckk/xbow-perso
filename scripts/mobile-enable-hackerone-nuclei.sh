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

cd "$INSTALL_DIR"
chmod 600 "$SECRETS_FILE"

# Always converge the VPS onto the current safe production baseline first.
# This makes the activation command resilient when containers are stopped,
# the checkout is stale, or .env still contains old manually-edited gates.
# After the updater refreshes the checkout, restart this script once so the
# remaining activation uses the newest code instead of the stale shell process.
if [ "${XBOW_ACTIVATION_REFRESHED:-0}" != "1" ]; then
  echo "=== SAFE PRODUCTION REFRESH ==="
  bash "$INSTALL_DIR/scripts/mobile-production-update.sh"
  echo "=== RESTART ACTIVATION FROM UPDATED CHECKOUT ==="
  exec env XBOW_ACTIVATION_REFRESHED=1 bash "$INSTALL_DIR/scripts/mobile-enable-hackerone-nuclei.sh"
fi

# The refreshed invocation continues with the now-running stack while the
# repository .env remains fail-safe.
cd "$INSTALL_DIR"

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

COMPOSE=(
  docker compose
  -f docker-compose.yml
  -f docker-compose.distributed.yml
  -f docker-compose.tls.yml
)

echo "=== BACKEND READINESS ==="
"${COMPOSE[@]}" exec -T backend python -m app.readiness

echo "=== RECONCILE HACKERONE BATCH STATE ==="
"${COMPOSE[@]}" exec -T backend python - <<'PY'
from app.hackerone_batch import reconcile_hackerone_batches
from app.main import queue, storage

count = reconcile_hackerone_batches(queue(), storage(), limit=200)
print(f"RECONCILED_BATCHES={count}")
PY

echo "=== QUEUE MUST BE IDLE BEFORE ARMING ==="
"${COMPOSE[@]}" exec -T backend python - <<'PY'
from app.main import queue, storage

stats = queue().stats()
queued = int(stats["by_status"].get("queued", 0))
running = int(stats["by_status"].get("running", 0))
active_jobs = queued + running
active_batches = [
    batch
    for batch in storage().list_hackerone_batches(limit=50)
    if str(batch.get("state") or "") not in {"completed", "cancelled"}
]
queue_idle = active_jobs == 0 and not active_batches
print("QUEUE_IDLE=" + ("true" if queue_idle else "false"))
print(f"QUEUE_QUEUED={queued}")
print(f"QUEUE_RUNNING={running}")
if active_batches:
    print("ACTIVE_BATCH_ID=" + str(active_batches[0].get("id") or ""))
    print("ACTIVE_BATCH_STATE=" + str(active_batches[0].get("state") or ""))
if not queue_idle:
    print("NEXT_STEP=Let the active batch finish or cancel it from the dashboard before arming the scanner.")
    raise SystemExit(1)
PY

TMP_PROFILE="$(mktemp)"
cleanup_tmp() {
  rm -f "$TMP_PROFILE"
}
trap cleanup_tmp EXIT

cat >"$TMP_PROFILE" <<'EOF'
DRY_RUN=false
XBOW_ENABLE_ACTIVE_SCANS=true
XBOW_ENABLE_SCANNER_WORKER=true
XBOW_ENABLE_NUCLEI=true
XBOW_ENABLE_RECON=true
XBOW_ENABLE_EXTERNAL_RECON=false
XBOW_ENABLE_BROWSER_AUTOMATION=false
XBOW_SCAN_ENGINES=nuclei
XBOW_SCANNER_ALLOWED_ENGINES=nuclei
XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1
XBOW_NUCLEI_ALLOWED_VERSION=3.11.1
XBOW_MAX_AUTONOMOUS_RPS=2.0
XBOW_ENABLE_HACKERONE_SUBMISSION=false
EOF
chmod 600 "$TMP_PROFILE"

rollback() {
  status=$?
  trap - ERR
  echo "Activation failed; restoring safe production mode." >&2
  rm -f "$LIVE_PROFILE_FILE"
  bash "$INSTALL_DIR/scripts/mobile-production-update.sh" || true
  exit "$status"
}
trap rollback ERR

install -m 600 "$TMP_PROFILE" "$LIVE_PROFILE_FILE"

echo "=== ARM PERSISTENT HACKERONE NUCLEI PROFILE ==="
bash "$INSTALL_DIR/scripts/mobile-production-update.sh"

echo
echo "=== HACKERONE API PROBE ==="
"${COMPOSE[@]}" --profile scanner exec -T backend python - <<'PY'
from app.hackerone_client import HackerOneClient, HackerOneClientError, load_hackerone_credentials

try:
    credentials = load_hackerone_credentials()
    HackerOneClient(credentials).get_json(
        "hackers/programs",
        {"page[number]": 1, "page[size]": 1},
    )
except HackerOneClientError as exc:
    print("HACKERONE_API_READY=false")
    print("HACKERONE_API_ERROR=" + exc.__class__.__name__)
    raise SystemExit(1)
print("HACKERONE_API_READY=true")
PY
echo
echo "PERSISTENT HACKERONE NUCLEI PROFILE ARMED"
echo "The root-only profile survives normal production updates."
echo "Bounded builtin recon is enabled; external recon and browser automation remain disabled."
echo "Every campaign still requires verified HackerOne scope/policy/fingerprint admission."
echo "HackerOne report submission remains disabled."
echo
echo "=== FINAL BUG BOUNTY LAUNCH VERDICT ==="
"${COMPOSE[@]}" --profile scanner exec -T backend python - <<'PY'
from app.hackerone_live_readiness import build_hackerone_live_readiness
from app.main import dependency_readiness

result = build_hackerone_live_readiness(dependency_readiness())
failed = [
    item for item in result.get("checks", [])
    if item.get("required") is True and item.get("ok") is not True
]
if failed:
    print("BUG_BOUNTY_LAUNCH_READY=false")
    for item in failed:
        print("BLOCKER=" + str(item.get("id") or "unknown") + " | " + str(item.get("label") or ""))
    raise SystemExit(1)
print("BUG_BOUNTY_LAUNCH_READY=true")
print("NEXT_STEP=Open the dashboard, review any first-run policies, then press Commencer.")
PY

trap - ERR

PUBLIC_HOST="$(read_env_value XBOW_PUBLIC_HOST)"
if [ -n "$PUBLIC_HOST" ]; then
  echo "DASHBOARD_URL=https://$PUBLIC_HOST/"
fi
