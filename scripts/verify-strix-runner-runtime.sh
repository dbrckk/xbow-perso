#!/usr/bin/env bash
set -euo pipefail

docker compose --profile strix-runner run   --rm   --no-deps   -T   strix-runner   python -m app.strix_runner_attestation --check

docker compose --profile strix-runner run   --rm   --no-deps   -T   strix-runner   python - <<'PY'
import socket

try:
    connection = socket.create_connection(("1.1.1.1", 443), timeout=2.0)
except OSError:
    raise SystemExit(0)

connection.close()
raise SystemExit("direct public TCP egress unexpectedly available")
PY
