This file is a merged representation of a subset of the codebase, containing specifically included files and files not matching ignore patterns, combined into a single document by Repomix.
The content has been processed where content has been compressed (code blocks are separated by ⋮---- delimiter).

# File Summary

## Purpose
This file contains a packed representation of a subset of the repository's contents that is considered the most important context.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Only files matching these patterns are included: **/*.{py,js,mjs,cjs,ts,tsx,jsx,java,kt,kts,gd,groovy,gradle,toml,json,yaml,yml,sql,sh}
- Files matching these patterns are excluded: .ai/**, **/node_modules/**, **/.gradle/**, **/build/**, **/dist/**, **/.venv/**, **/__pycache__/**, **/.pytest_cache/**, **/.git/**, **/coverage/**, **/*.lock, **/*.min.js, **/*.map, assets/**, art/**, art_sources/**, marketing/**, colab/**, kaggle/**, discovery-cache.json, health-snapshot.json, history.json
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Content has been compressed - code blocks are separated by ⋮---- delimiter
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
```
bootstrap-mobile-ubuntu.sh
mobile-disable-hackerone-nuclei.sh
mobile-enable-hackerone-nuclei.sh
mobile-production-cutover.sh
mobile-production-preflight.sh
mobile-production-rollback.sh
mobile-production-status.sh
mobile-production-update.sh
mobile-vault-cutover.sh
mobile-vault-rollback.sh
```

# Files

## File: bootstrap-mobile-ubuntu.sh
```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${XBOW_REPO_URL:-https://github.com/dbrckk/xbow-perso.git}"
INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
RUN_USER="${SUDO_USER:-$USER}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git openssl

if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable"     > /etc/apt/sources.list.d/docker.list
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker

if [ ! -d "$INSTALL_DIR/.git" ]; then
  rm -rf "$INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" fetch --prune origin
  git -C "$INSTALL_DIR" checkout main
  git -C "$INSTALL_DIR" reset --hard origin/main
fi

cp -n "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"

# The bootstrap itself runs as root, but subsequent Git maintenance is performed
# by the interactive operator account. Hand the checkout back to that account
# to avoid Git safe.directory/dubious-ownership failures on later updates.
chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env"

API_TOKEN="$(openssl rand -hex 32)"
python3 - "$INSTALL_DIR/.env" "$API_TOKEN" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
token = sys.argv[2]
lines = p.read_text().splitlines()
updates = {
    "XBOW_API_TOKEN": token,
    "DRY_RUN": "true",
    "XBOW_ENABLE_ACTIVE_SCANS": "false",
    "XBOW_ENABLE_NUCLEI": "false",
    "XBOW_ENABLE_HACKERONE_SUBMISSION": "false",
}
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0]
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
p.write_text("\n".join(out) + "\n")
PY

install -m 600 /dev/null /root/xbow-bootstrap-secrets.txt
printf 'XBOW_API_TOKEN=%s\n' "$API_TOKEN" > /root/xbow-bootstrap-secrets.txt

cd "$INSTALL_DIR"
docker compose config >/dev/null
docker compose up -d --build

echo
echo "xbow-perso base stack installed with SAFE gates closed."
echo "API token stored in /root/xbow-bootstrap-secrets.txt (mode 600)."
echo "Do not enable active scans until the exact HackerOne program policy/scope is reviewed."
echo "Next: configure HTTPS/private access, HackerOne credentials, then use the PWA preflight."
```

## File: mobile-disable-hackerone-nuclei.sh
```bash
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
LIVE_PROFILE_FILE="${XBOW_LIVE_SCANNER_PROFILE_FILE:-/root/xbow-live-scanner.env}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [ ! -d "$INSTALL_DIR/.git" ] || [ ! -f "$INSTALL_DIR/.env" ]; then
  echo "xbow-perso installation not found at $INSTALL_DIR" >&2
  exit 1
fi

rm -f "$LIVE_PROFILE_FILE"

echo "=== DISARM PERSISTENT NUCLEI PROFILE ==="
bash "$INSTALL_DIR/scripts/mobile-production-update.sh"

echo
echo "PERSISTENT HACKERONE NUCLEI PROFILE DISARMED"
echo "Production is back on the fail-safe .env baseline."
```

## File: mobile-enable-hackerone-nuclei.sh
```bash
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

echo "=== QUEUE MUST BE IDLE BEFORE ARMING ==="
"${COMPOSE[@]}" exec -T backend python -c \
  'from app.main import queue; s=queue().stats(); active=int(s["by_status"].get("queued",0))+int(s["by_status"].get("running",0)); assert active==0, s; print(s)'

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

trap - ERR
echo
echo "PERSISTENT HACKERONE NUCLEI PROFILE ARMED"
echo "The root-only profile survives normal production updates."
echo "Bounded builtin recon is enabled; external recon and browser automation remain disabled."
echo "Every campaign still requires verified HackerOne scope/policy/fingerprint admission."
echo "HackerOne report submission remains disabled."
```

## File: mobile-production-cutover.sh
```bash
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${XBOW_INSTALL_DIR:-/opt/xbow-perso}"
SECRETS_FILE="${XBOW_PRODUCTION_SECRETS_FILE:-/root/xbow-production-secrets.env}"
STATUS_FILE="${XBOW_MIGRATION_STATUS_FILE:-/root/xbow-storage-migration-status.json}"

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
  echo "Run scripts/mobile-production-preflight.sh first." >&2
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
git_as_owner fetch --prune origin
git_as_owner checkout main
git_as_owner reset --hard origin/main

echo "=== BUILD CURRENT BACKEND IMAGE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml build backend

echo "=== VALIDATE COMPOSE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml config --quiet

echo "=== START DATABASE SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml up -d postgres redis

echo "=== WAIT FOR DATABASE SERVICES ==="
for _ in $(seq 1 45); do
  pg_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q postgres)" 2>/dev/null || true)"
  redis_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q redis)" 2>/dev/null || true)"
  if [ "$pg_health" = "healthy" ] && [ "$redis_health" = "healthy" ]; then
    break
  fi
  sleep 2
done

pg_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q postgres)" 2>/dev/null || true)"
redis_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q redis)" 2>/dev/null || true)"
if [ "$pg_health" != "healthy" ] || [ "$redis_health" != "healthy" ]; then
  echo "Database services are not healthy; refusing cutover." >&2
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps postgres redis
  exit 1
fi

echo "=== FINAL READ-ONLY MIGRATION PLAN ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps \
  -e XBOW_MIGRATION_SQLITE_PATH=/data/xbow.sqlite3 \
  -e XBOW_ARTIFACT_ROOT=/data/artifacts \
  -e XBOW_DATABASE_URL="$XBOW_DATABASE_URL" \
  -e XBOW_REDIS_URL="$XBOW_REDIS_URL" \
  backend python -m app.production_migration plan

echo "=== QUIESCE APPLICATION ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml stop \
  tls-proxy frontend worker backend || true

for profile_service in scanner-worker pentagi-worker pentagi-status-worker hackerone-report-sync-worker; do
  container_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q "$profile_service" 2>/dev/null || true)"
  if [ -n "$container_id" ]; then
    docker stop "$container_id" >/dev/null
  fi
done

echo "=== APPLY STORAGE MIGRATION ==="
set +e
migration_output="$(
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps \
    -e XBOW_MIGRATION_QUIESCED=true \
    -e XBOW_MIGRATION_SQLITE_PATH=/data/xbow.sqlite3 \
    -e XBOW_ARTIFACT_ROOT=/data/artifacts \
    -e XBOW_DATABASE_URL="$XBOW_DATABASE_URL" \
    -e XBOW_REDIS_URL="$XBOW_REDIS_URL" \
    backend python -m app.production_migration apply 2>&1
)"
migration_rc=$?
set -e

printf '%s\n' "$migration_output"
if [ "$migration_rc" -ne 0 ]; then
  echo "Migration failed. Restarting the previous SQLite application stack." >&2
  docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build backend worker frontend tls-proxy
  exit "$migration_rc"
fi

printf '%s\n' "$migration_output" > "$STATUS_FILE"
chmod 600 "$STATUS_FILE"

echo "=== START DISTRIBUTED STACK ==="
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

backend_id="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps -q backend)"
backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$backend_id" 2>/dev/null || true)"
if [ "$backend_health" != "healthy" ]; then
  echo "Distributed backend failed health validation." >&2
  echo "Rollback command: sudo bash $INSTALL_DIR/scripts/mobile-production-rollback.sh" >&2
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps
  exit 1
fi

echo "=== READINESS ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness

echo "=== SERVICES ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps

PUBLIC_HOST="$(read_env_value XBOW_PUBLIC_HOST)"
if [ -n "$PUBLIC_HOST" ]; then
  echo "=== HTTPS ==="
  curl -fsSI "https://$PUBLIC_HOST" | sed -n '1,12p'
fi

echo
echo "STORAGE CUTOVER COMPLETE"
echo "SQLite source remains unchanged and a migration backup was created."
echo "Migration status saved to $STATUS_FILE (mode 600)."
echo "Safe scan/submission gates remain closed."
echo "Vault cutover has NOT been performed yet."
```

## File: mobile-production-preflight.sh
```bash
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
  local value
  value="$(grep -E "^[[:space:]]*${key}=" .env | tail -n1 | cut -d= -f2- || true)"
  printf '%s' "$value"
}

require_gate() {
  local key="$1"
  local expected="$2"
  local actual
  actual="$(read_env_value "$key" | tr '[:upper:]' '[:lower:]')"
  if [ "$actual" != "$expected" ]; then
    echo "SAFE-GATE BLOCK: $key must be $expected before production migration preflight" >&2
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

if [ ! -f "$SECRETS_FILE" ]; then
  install -m 600 /dev/null "$SECRETS_FILE"
  POSTGRES_PASSWORD="$(openssl rand -hex 32)"
  REDIS_PASSWORD="$(openssl rand -hex 32)"
  printf 'XBOW_POSTGRES_PASSWORD=%s\n' "$POSTGRES_PASSWORD" >> "$SECRETS_FILE"
  printf 'XBOW_REDIS_PASSWORD=%s\n' "$REDIS_PASSWORD" >> "$SECRETS_FILE"
else
  chmod 600 "$SECRETS_FILE"
fi

# shellcheck disable=SC1090
. "$SECRETS_FILE"

: "${XBOW_POSTGRES_PASSWORD:?missing XBOW_POSTGRES_PASSWORD in $SECRETS_FILE}"
: "${XBOW_REDIS_PASSWORD:?missing XBOW_REDIS_PASSWORD in $SECRETS_FILE}"

export XBOW_POSTGRES_PASSWORD
export XBOW_REDIS_PASSWORD
export XBOW_POSTGRES_DB="${XBOW_POSTGRES_DB:-xbow}"
export XBOW_POSTGRES_USER="${XBOW_POSTGRES_USER:-xbow}"
export XBOW_DATABASE_URL="postgresql://${XBOW_POSTGRES_USER}:${XBOW_POSTGRES_PASSWORD}@postgres:5432/${XBOW_POSTGRES_DB}"
export XBOW_REDIS_URL="redis://:${XBOW_REDIS_PASSWORD}@redis:6379/0"

echo "=== UPDATE ==="
git_as_owner fetch --prune origin
git_as_owner checkout main
git_as_owner reset --hard origin/main

echo "=== BUILD CURRENT BACKEND IMAGE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml build backend

echo "=== COMPOSE VALIDATION ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml config --quiet

echo "=== START POSTGRES + REDIS ONLY ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml up -d postgres redis

echo "=== WAIT FOR DEPENDENCIES ==="
for _ in $(seq 1 45); do
  pg_ok="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps --format json postgres 2>/dev/null | grep -c '"Health":"healthy"' || true)"
  redis_ok="$(docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps --format json redis 2>/dev/null | grep -c '"Health":"healthy"' || true)"
  if [ "$pg_ok" -gt 0 ] && [ "$redis_ok" -gt 0 ]; then
    break
  fi
  sleep 2
done

echo "=== DEPENDENCY STATUS ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml ps postgres redis

echo "=== MIGRATION PLAN ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps   -e XBOW_MIGRATION_SQLITE_PATH=/data/xbow.sqlite3   -e XBOW_ARTIFACT_ROOT=/data/artifacts   -e XBOW_DATABASE_URL="$XBOW_DATABASE_URL"   -e XBOW_REDIS_URL="$XBOW_REDIS_URL"   backend python -m app.production_migration plan

echo "=== VAULT MIGRATION ==="
echo "Deferred: vault migration has a separate verified cutover step."

echo
echo "PRE-FLIGHT COMPLETE"
echo "No scanner service was started."
echo "Safe gates remain unchanged."
echo "Generated PostgreSQL/Redis credentials are stored only in $SECRETS_FILE (mode 600)."
echo "Do not share or screenshot that file."
```

## File: mobile-production-rollback.sh
```bash
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
```

## File: mobile-production-status.sh
```bash
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
else
  echo "armed=false"
fi
```

## File: mobile-production-update.sh
```bash
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
```

## File: mobile-vault-cutover.sh
```bash
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
git_as_owner fetch --prune origin
git_as_owner checkout main
git_as_owner reset --hard origin/main

echo "=== BUILD CURRENT BACKEND IMAGE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml build backend

echo "=== VERIFY DISTRIBUTED STORAGE ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend python -m app.readiness
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml exec -T backend \
  python -c 'import os; assert os.getenv("XBOW_STORAGE_BACKEND") == "postgresql"; assert os.getenv("XBOW_QUEUE_BACKEND") == "redis"; print("distributed-backends=ok")'

LEGACY_SOURCE_PATH="/data/.vault-migration-source.env"
cleanup_legacy_source() {
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps -T \
    backend sh -c 'rm -f /data/.vault-migration-source.env' >/dev/null 2>&1 || true
}
trap cleanup_legacy_source EXIT

echo "=== STAGE PRIVATE LEGACY ENV ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps -T \
  backend sh -c 'umask 077; cat > /data/.vault-migration-source.env' < "$ENV_FILE"

echo "=== VAULT MIGRATION PLAN ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps \
  -e XBOW_VAULT_ENABLED=false \
  -e XBOW_VAULT_PATH=/data/secrets.vault.json \
  -e XBOW_VAULT_MASTER_KEY_FILE=/data/vault-master.key \
  backend python -m app.vault_migration plan --source-env-file "$LEGACY_SOURCE_PATH"

echo "=== VAULT MIGRATION APPLY ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps \
  -e XBOW_VAULT_ENABLED=false \
  -e XBOW_VAULT_PATH=/data/secrets.vault.json \
  -e XBOW_VAULT_MASTER_KEY_FILE=/data/vault-master.key \
  backend python -m app.vault_migration apply --source-env-file "$LEGACY_SOURCE_PATH"

echo "=== VERIFY REQUIRED VAULT AUTH SECRET ==="
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps \
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
  docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml run --rm --no-deps \
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
```

## File: mobile-vault-rollback.sh
```bash
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
```
