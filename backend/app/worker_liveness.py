from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ALLOWED_ROLES = {"general", "scanner"}
_DEFAULT_ROOT = "/data/worker-heartbeats"


def _root() -> Path:
    raw = (os.getenv("XBOW_WORKER_HEARTBEAT_ROOT") or _DEFAULT_ROOT).strip()
    if not raw:
        raise ValueError("XBOW_WORKER_HEARTBEAT_ROOT must not be blank")
    return Path(raw)


def _max_age_seconds() -> int:
    raw = (os.getenv("XBOW_WORKER_HEARTBEAT_MAX_AGE_SECONDS") or "30").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_WORKER_HEARTBEAT_MAX_AGE_SECONDS must be an integer") from exc
    if not 5 <= value <= 300:
        raise ValueError("XBOW_WORKER_HEARTBEAT_MAX_AGE_SECONDS must be between 5 and 300")
    return value


def _role(value: str) -> str:
    role = value.strip().lower()
    if role not in _ALLOWED_ROLES:
        raise ValueError("worker heartbeat role must be general or scanner")
    return role


def _path(role: str) -> Path:
    return _root() / f"{_role(role)}.json"


def write_worker_heartbeat(role: str) -> None:
    safe_role = _role(role)
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "role": safe_role,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    target = root / f"{safe_role}.json"
    temporary = root / f".{safe_role}.{os.getpid()}.tmp"
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    if os.name == "posix":
        temporary.chmod(0o600)
    os.replace(temporary, target)


def worker_liveness(role: str, *, now: datetime | None = None) -> dict[str, Any]:
    safe_role = _role(role)
    max_age = _max_age_seconds()
    target = _path(safe_role)
    current = now or datetime.now(timezone.utc)

    try:
        raw = target.read_text(encoding="utf-8")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("heartbeat document must be an object")
        if document.get("version") != 1 or document.get("role") != safe_role:
            raise ValueError("heartbeat identity mismatch")
        observed = datetime.fromisoformat(str(document.get("observed_at") or ""))
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("heartbeat timestamp must be timezone-aware")
        age = max(0, int((current - observed.astimezone(timezone.utc)).total_seconds()))
    except FileNotFoundError:
        return {
            "role": safe_role,
            "live": False,
            "reason": "heartbeat_missing",
            "max_age_seconds": max_age,
            "contains_secrets": False,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {
            "role": safe_role,
            "live": False,
            "reason": "heartbeat_invalid",
            "max_age_seconds": max_age,
            "contains_secrets": False,
        }

    live = age <= max_age
    return {
        "role": safe_role,
        "live": live,
        "reason": None if live else "heartbeat_stale",
        "age_seconds": age,
        "max_age_seconds": max_age,
        "contains_secrets": False,
    }


def worker_liveness_snapshot() -> dict[str, Any]:
    try:
        general = worker_liveness("general")
        scanner = worker_liveness("scanner")
    except ValueError:
        general = {
            "role": "general",
            "live": False,
            "reason": "heartbeat_configuration_invalid",
            "contains_secrets": False,
        }
        scanner = {
            "role": "scanner",
            "live": False,
            "reason": "heartbeat_configuration_invalid",
            "contains_secrets": False,
        }
    return {
        "general": general,
        "scanner": scanner,
        "contains_secrets": False,
    }
