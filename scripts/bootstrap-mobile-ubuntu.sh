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
