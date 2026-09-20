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
