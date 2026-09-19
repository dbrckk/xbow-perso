#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "Docker is required on the VPS."
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is required (docker compose)."
command -v openssl >/dev/null 2>&1 || fail "openssl is required."

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
fi

set_env() {
  local key="$1"
  local value="$2"
  if grep -q "^$key=" .env; then
    sed -i "s|^$key=.*|$key=$value|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

current_token="$(grep '^XBOW_API_TOKEN=' .env | head -n1 | cut -d= -f2- || true)"
if [[ -z "$current_token" ]]; then
  set_env "XBOW_API_TOKEN" "$(openssl rand -hex 32)"
fi

# Safe initial state. Real scanning is enabled only after a specific HackerOne
# program has been loaded and its current policy/scope has been reviewed.
set_env "DRY_RUN" "true"
set_env "XBOW_ENABLE_ACTIVE_SCANS" "false"
set_env "XBOW_ENABLE_NUCLEI" "false"
set_env "XBOW_ENABLE_HACKERONE_SUBMISSION" "false"
set_env "XBOW_ENABLE_PENTAGI" "false"
set_env "XBOW_SCANNER_ALLOWED_ENGINES" "nuclei"
set_env "XBOW_SCANNER_SANDBOX_PROFILE" "restricted-v1"

chmod 600 .env

docker compose up -d --build

printf '\nWaiting for xbow-perso health endpoint...\n'
ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done

if [[ "$ok" != "1" ]]; then
  docker compose ps >&2 || true
  fail "xbow-perso did not become healthy. Check: docker compose logs --tail=200"
fi

printf '\nxbow-perso is running in SAFE MODE.\n'
printf 'PWA: http://SERVER_IP:8080\n'
printf 'Active scans: disabled\n'
printf 'Dry run: enabled\n'
printf 'HackerOne direct submission: disabled\n'
printf '\nNext: configure HackerOne server credentials, then use the PWA preflight.\n'
printf 'Guide: SMARTPHONE_ONLY.md and FIRST_REAL_HACKERONE_RUN.md\n'
