from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from .hackerone_client import HackerOneClient, HackerOneClientError
from .storage import CampaignConflictError


CATALOG_ID = "current"
_next_attempt_monotonic = 0.0


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_program_resource(resource: Any) -> dict[str, Any]:
    if not isinstance(resource, dict):
        raise HackerOneClientError("HackerOne program list contains an invalid resource")
    attributes = resource.get("attributes")
    if not isinstance(attributes, dict):
        raise HackerOneClientError("HackerOne program list contains invalid attributes")
    handle = attributes.get("handle")
    name = attributes.get("name")
    if not isinstance(handle, str) or not handle or not isinstance(name, str) or not name:
        raise HackerOneClientError("HackerOne program list contains invalid identity fields")
    return {
        "handle": handle,
        "name": name,
        "submission_state": attributes.get("submission_state"),
        "state": attributes.get("state"),
        "offers_bounties": attributes.get("offers_bounties"),
        "gold_standard_safe_harbor": attributes.get("gold_standard_safe_harbor"),
    }


def fetch_hackerone_program_catalog(
    *,
    client: HackerOneClient | None = None,
) -> list[dict[str, Any]]:
    api = client or HackerOneClient()
    resources = api.get_all_pages("hackers/programs")
    programs = [normalize_program_resource(resource) for resource in resources]
    programs.sort(key=lambda item: (str(item["name"]).lower(), str(item["handle"])))
    return programs


def _fingerprint(programs: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        programs,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _diff_programs(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> dict[str, list[str]]:
    old = {str(item["handle"]): item for item in previous}
    new = {str(item["handle"]): item for item in current}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(
        handle
        for handle in set(old).intersection(new)
        if old[handle] != new[handle]
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def refresh_hackerone_catalog(
    store,
    *,
    client: HackerOneClient | None = None,
) -> dict[str, Any]:
    programs = fetch_hackerone_program_catalog(client=client)
    fingerprint = _fingerprint(programs)
    checked_at = _utcnow()

    for _ in range(3):
        record = store.get_hackerone_catalog_state_record(CATALOG_ID)
        if record is None:
            state = {
                "id": CATALOG_ID,
                "provider": "hackerone",
                "programs": programs,
                "fingerprint": fingerprint,
                "checked_at": checked_at,
                "updated_at": checked_at,
                "changed_at": None,
                "change_sequence": 0,
                "changes": {
                    "added": [],
                    "removed": [],
                    "changed": [],
                },
                "background_monitor": True,
            }
            try:
                store.save_hackerone_catalog_state(state, expected_version=0)
                return state
            except CampaignConflictError:
                continue

        previous, version = record
        same = str(previous.get("fingerprint") or "") == fingerprint
        if same:
            changes = previous.get("changes")
            if not isinstance(changes, dict):
                changes = {"added": [], "removed": [], "changed": []}
            state = {
                **previous,
                "programs": programs,
                "fingerprint": fingerprint,
                "checked_at": checked_at,
                "updated_at": checked_at,
                "changes": changes,
                "background_monitor": True,
            }
        else:
            changes = _diff_programs(
                list(previous.get("programs") or []),
                programs,
            )
            state = {
                **previous,
                "programs": programs,
                "fingerprint": fingerprint,
                "checked_at": checked_at,
                "updated_at": checked_at,
                "changed_at": checked_at,
                "change_sequence": int(previous.get("change_sequence") or 0) + 1,
                "changes": changes,
                "background_monitor": True,
            }

        try:
            store.save_hackerone_catalog_state(state, expected_version=version)
            return state
        except CampaignConflictError:
            continue

    latest = store.get_hackerone_catalog_state(CATALOG_ID)
    if latest is None:
        raise CampaignConflictError("HackerOne catalog update conflicted")
    return latest


def _strict_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def catalog_poll_seconds() -> int:
    raw = (os.getenv("XBOW_HACKERONE_CATALOG_POLL_SECONDS") or "900").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            "XBOW_HACKERONE_CATALOG_POLL_SECONDS must be an integer"
        ) from exc
    if not 300 <= value <= 86400:
        raise ValueError(
            "XBOW_HACKERONE_CATALOG_POLL_SECONDS must be between 300 and 86400"
        )
    return value


def maybe_refresh_hackerone_catalog(store) -> dict[str, Any]:
    global _next_attempt_monotonic

    if not _strict_bool_env("XBOW_ENABLE_HACKERONE_CATALOG_MONITOR", True):
        return {"status": "disabled"}

    now = time.monotonic()
    if now < _next_attempt_monotonic:
        return {"status": "not_due"}

    interval = catalog_poll_seconds()
    _next_attempt_monotonic = now + interval
    try:
        state = refresh_hackerone_catalog(store)
    except HackerOneClientError:
        return {"status": "unavailable"}
    except CampaignConflictError:
        return {"status": "conflict"}
    return {
        "status": "refreshed",
        "fingerprint": state.get("fingerprint"),
        "checked_at": state.get("checked_at"),
    }
