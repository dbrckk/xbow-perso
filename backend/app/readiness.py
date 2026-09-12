from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .queue_backend import create_queue
from .storage_backend import create_storage


# Backward-compatible test seam; runtime still resolves through create_storage().
def Storage():
    return create_storage()


# Backward-compatible test seam; runtime resolves through create_queue().
def JobQueue():
    return create_queue()


def _artifact_store_ready(root: Path) -> dict[str, Any]:
    """Verify that the configured artifact store is writable by this process."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".xbow-ready-", dir=root, delete=True):
            pass
    except OSError as exc:
        return {"ok": False, "error": exc.__class__.__name__}
    return {"ok": True}


def readiness() -> dict[str, Any]:
    """Return dependency readiness without exposing queue payloads or secrets."""
    try:
        queue = JobQueue().health()
    except Exception as exc:  # pragma: no cover - defensive boundary for container probes
        queue = {"ok": False, "error": exc.__class__.__name__}

    try:
        store = Storage()
        metadata = store.health()
    except Exception as exc:  # pragma: no cover - defensive boundary for container probes
        store = None
        metadata = {"ok": False, "error": exc.__class__.__name__}

    if store is None:
        artifacts = {"ok": False, "error": "StorageUnavailable"}
    else:
        artifacts = _artifact_store_ready(store.artifact_root)

    return {
        "ok": (
            bool(queue.get("ok"))
            and bool(metadata.get("ok"))
            and bool(artifacts.get("ok"))
        ),
        "queue": queue,
        "metadata": metadata,
        "artifacts": artifacts,
    }


def main() -> None:
    result = readiness()
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
