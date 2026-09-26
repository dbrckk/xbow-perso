from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from .hackerone_client import HackerOneClientError, fetch_hackerone_program_snapshot
from .hackerone_review_draft import (
    build_hackerone_review_draft,
    review_draft_blockers,
    review_draft_is_usable,
)
from .storage import CampaignConflictError


_next_attempt_monotonic = 0.0

_CAPABILITY_GAPS = {
    "hackerone_response_not_json": {
        "capability": "hackerone_jsonapi_transport",
        "description": "Adapter le client aux media types JSON renvoyés par les endpoints HackerOne.",
    },
    "hackerone_response_shape_invalid": {
        "capability": "hackerone_response_adapter",
        "description": "Adapter le parseur à la forme actuelle de la réponse HackerOne sans relâcher les contrôles de scope.",
    },
    "hackerone_structured_scope_invalid": {
        "capability": "hackerone_scope_adapter",
        "description": "Adapter l'import du Structured Scope à la forme actuelle renvoyée par HackerOne.",
    },
    "no_compatible_primary_domain": {
        "capability": "wildcard_or_path_bootstrap",
        "description": "Ajouter un démarrage sûr pour les scopes wildcard/URL sans cible web exacte.",
    },
    "no_bounty_eligible_primary_target": {
        "capability": "bounty_target_selection",
        "description": "Le programme paie des bounties mais les cibles web compatibles inspectées sont explicitement non éligibles au bounty.",
    },
    "scope_incomplete_for_web_engine": {
        "capability": "path_or_network_aware_scope",
        "description": "Ajouter des règles de scope URL/CIDR plus granulaires sans élargir le périmètre.",
    },
    "scope_exclusions_require_manual_enforcement": {
        "capability": "structured_scope_exclusion_enforcement",
        "description": "Transformer les exclusions HackerOne en règles machine vérifiables avant tout scan.",
    },
    "policy_text_unavailable": {
        "capability": "policy_visibility",
        "description": "Aucune automatisation sûre sans texte de politique vérifiable.",
    },
    "review_unavailable": {
        "capability": "upstream_availability",
        "description": "Réessayer plus tard; ce blocage n'implique pas une incompatibilité du projet.",
    },
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strict_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def feasibility_poll_seconds() -> int:
    return _strict_int_env(
        "XBOW_HACKERONE_FEASIBILITY_POLL_SECONDS",
        300,
        300,
        86400,
    )


def feasibility_batch_size() -> int:
    return _strict_int_env(
        "XBOW_HACKERONE_FEASIBILITY_BATCH_SIZE",
        4,
        1,
        12,
    )


def feasibility_initial_batch_size() -> int:
    return _strict_int_env(
        "XBOW_HACKERONE_FEASIBILITY_INITIAL_BATCH_SIZE",
        12,
        4,
        24,
    )


def _open_bounty(program: dict[str, Any]) -> bool:
    if program.get("offers_bounties") is not True:
        return False
    if str(program.get("submission_state") or "").strip().lower() in {
        "closed",
        "paused",
        "disabled",
    }:
        return False
    return str(program.get("state") or "").strip().lower() not in {
        "closed",
        "disabled",
        "archived",
    }


def _checked_sort_key(
    handle: str,
    existing: dict[str, dict[str, Any]],
) -> tuple[int, str, str]:
    record = existing.get(handle)
    if not isinstance(record, dict):
        return (0, "", handle)
    if record.get("retryable") is True:
        return (0, str(record.get("checked_at") or ""), handle)
    return (1, str(record.get("checked_at") or ""), handle)


def _client_failure_reason(exc: HackerOneClientError) -> tuple[str, bool]:
    message = str(exc).lower()
    status = exc.status_code
    if status == 429:
        return "hackerone_rate_limited", True
    if status is not None and status >= 500:
        return "hackerone_upstream_unavailable", True
    if "timed out" in message:
        return "hackerone_timeout", True
    if "connection failed" in message:
        return "hackerone_connection_failed", True
    if "i/o failed" in message:
        return "hackerone_io_failed", True
    if "not json" in message:
        return "hackerone_response_not_json", False
    if "structured scope is invalid" in message:
        return "hackerone_structured_scope_invalid", False
    if (
        "response has no" in message
        or "response must be" in message
        or "paginated response" in message
        or "program policy is invalid" in message
        or "program name is invalid" in message
        or "handle mismatch" in message
    ):
        return "hackerone_response_shape_invalid", False
    if status in {401, 403, 404}:
        return f"hackerone_http_{status}", False
    return "hackerone_snapshot_invalid", False


def _inspect_handle(handle: str) -> dict[str, Any]:
    try:
        snapshot = fetch_hackerone_program_snapshot(handle)
    except HackerOneClientError as exc:
        status = exc.status_code
        reason, retryable = _client_failure_reason(exc)
        return {
            "handle": handle,
            "status": "unavailable" if retryable else "blocked",
            "project_compatible": None if retryable else False,
            "blockers": ["review_unavailable"] if retryable else [reason],
            "failure_reason": reason,
            "retryable": retryable,
            "upstream_status": status,
            "checked_at": _utcnow(),
            "contains_secrets": False,
        }

    draft = build_hackerone_review_draft(snapshot)
    blockers = review_draft_blockers(draft)
    usable = review_draft_is_usable(draft)
    return {
        "handle": handle,
        "status": "compatible" if usable else "blocked",
        "project_compatible": usable,
        "blockers": blockers,
        "primary_url": str((draft.get("prefill") or {}).get("primary_url") or ""),
        "scope_mode": str((draft.get("prefill") or {}).get("scope_mode") or ""),
        "snapshot_sha256": str(snapshot.snapshot_sha256),
        "checked_at": _utcnow(),
        "contains_secrets": False,
    }


def refresh_hackerone_feasibility_batch(
    store,
    *,
    batch_size: int | None = None,
) -> dict[str, Any]:
    record = store.get_hackerone_catalog_state_record()
    if record is None:
        return {"status": "catalog_not_initialized", "checked": 0}

    catalog, version = record
    existing_raw = catalog.get("feasibility_index")
    existing = (
        {
            str(handle): dict(value)
            for handle, value in existing_raw.items()
            if isinstance(handle, str) and isinstance(value, dict)
        }
        if isinstance(existing_raw, dict)
        else {}
    )

    programmes = [
        dict(item)
        for item in list(catalog.get("programs") or [])
        if isinstance(item, dict) and _open_bounty(item)
    ]
    programmes.sort(
        key=lambda item: (
            0 if item.get("gold_standard_safe_harbor") is True else 1,
            _checked_sort_key(str(item.get("handle") or ""), existing),
            str(item.get("handle") or ""),
        )
    )

    if batch_size is not None:
        limit = batch_size
    elif not existing:
        limit = feasibility_initial_batch_size()
    else:
        limit = feasibility_batch_size()
    selected = [
        str(item.get("handle") or "")
        for item in programmes
        if str(item.get("handle") or "")
    ][: max(1, min(24, int(limit)))]

    if not selected:
        return {
            "status": "empty",
            "checked": 0,
            "compatible": 0,
            "indexed": len(existing),
        }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(2, len(selected))) as executor:
        futures = {
            executor.submit(_inspect_handle, handle): handle
            for handle in selected
        }
        for future in as_completed(futures):
            results.append(future.result())

    updated_index = dict(existing)
    for item in results:
        updated_index[str(item["handle"])] = item

    current_handles = {
        str(item.get("handle") or "")
        for item in programmes
        if str(item.get("handle") or "")
    }
    updated_index = {
        handle: value
        for handle, value in updated_index.items()
        if handle in current_handles
    }

    updated = {
        **catalog,
        "feasibility_index": updated_index,
        "feasibility_updated_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    try:
        store.save_hackerone_catalog_state(updated, expected_version=version)
    except CampaignConflictError:
        return {"status": "conflict", "checked": 0}

    compatible = sum(
        1
        for value in updated_index.values()
        if value.get("project_compatible") is True
    )
    return {
        "status": "refreshed",
        "checked": len(results),
        "compatible": compatible,
        "indexed": len(updated_index),
        "handles": sorted(item["handle"] for item in results),
    }


def maybe_refresh_hackerone_feasibility(store) -> dict[str, Any]:
    global _next_attempt_monotonic

    now = time.monotonic()
    if now < _next_attempt_monotonic:
        return {"status": "not_due"}

    _next_attempt_monotonic = now + feasibility_poll_seconds()
    return refresh_hackerone_feasibility_batch(store)


def feasibility_summary(
    catalog: dict[str, Any],
    *,
    limit: int = 100,
) -> dict[str, Any]:
    raw = catalog.get("feasibility_index")
    index = (
        {
            str(handle): dict(value)
            for handle, value in raw.items()
            if isinstance(handle, str) and isinstance(value, dict)
        }
        if isinstance(raw, dict)
        else {}
    )
    programmes = {
        str(item.get("handle") or ""): dict(item)
        for item in list(catalog.get("programs") or [])
        if isinstance(item, dict) and str(item.get("handle") or "")
    }

    compatible = []
    blocker_counts: dict[str, int] = {}
    unavailable_count = 0
    unavailable_reason_counts: dict[str, int] = {}
    for handle, record in index.items():
        if record.get("project_compatible") is True:
            program = programmes.get(handle, {})
            compatible.append(
                {
                    "handle": handle,
                    "name": str(program.get("name") or handle),
                    "gold_standard_safe_harbor": program.get(
                        "gold_standard_safe_harbor"
                    ),
                    "primary_url": str(record.get("primary_url") or ""),
                    "scope_mode": str(record.get("scope_mode") or ""),
                    "checked_at": record.get("checked_at"),
                    "snapshot_sha256": str(record.get("snapshot_sha256") or ""),
                    "automatic_launch": False,
                    "requires_launch_revalidation": True,
                }
            )
        elif record.get("project_compatible") is False:
            for reason in list(record.get("blockers") or []):
                key = str(reason)
                blocker_counts[key] = blocker_counts.get(key, 0) + 1
        else:
            unavailable_count += 1
            reason = str(record.get("failure_reason") or "review_unavailable")
            unavailable_reason_counts[reason] = unavailable_reason_counts.get(reason, 0) + 1

    compatible.sort(
        key=lambda item: (
            0 if item.get("gold_standard_safe_harbor") is True else 1,
            str(item.get("name") or "").lower(),
            str(item.get("handle") or ""),
        )
    )
    gap_rows = []
    for reason, count in sorted(
        blocker_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        gap = dict(_CAPABILITY_GAPS.get(reason) or {})
        gap_rows.append(
            {
                "reason": reason,
                "count": int(count),
                "capability": str(gap.get("capability") or "manual_review_or_new_adapter"),
                "description": str(
                    gap.get("description")
                    or "Analyser ce blocage avant d'ajouter une capacité au projet."
                ),
            }
        )

    safe_limit = max(1, min(500, int(limit)))
    return {
        "indexed": len(index),
        "compatible_count": len(compatible),
        "blocked_count": sum(
            1
            for value in index.values()
            if value.get("project_compatible") is False
        ),
        "unavailable_count": unavailable_count,
        "unavailable_reason_counts": dict(
            sorted(
                unavailable_reason_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "programs": compatible[:safe_limit],
        "blocker_counts": dict(
            sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "capability_gaps": gap_rows,
        "updated_at": catalog.get("feasibility_updated_at"),
        "read_only": True,
        "automatic_launch": False,
        "scope_expansion": False,
    }


def annotate_with_feasibility(
    programs: list[dict[str, Any]],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = catalog.get("feasibility_index")
    index = raw if isinstance(raw, dict) else {}
    result: list[dict[str, Any]] = []
    for item in programs:
        value = dict(item)
        handle = str(value.get("handle") or "")
        cached = index.get(handle)
        if isinstance(cached, dict):
            value["project_compatible"] = cached.get("project_compatible")
            value["feasibility_status"] = str(cached.get("status") or "")
            value["feasibility_blockers"] = list(cached.get("blockers") or [])
            value["feasibility_checked_at"] = cached.get("checked_at")
            value["feasibility_primary_url"] = str(cached.get("primary_url") or "")
        else:
            value["project_compatible"] = None
            value["feasibility_status"] = "unknown"
            value["feasibility_blockers"] = []
            value["feasibility_checked_at"] = None
            value["feasibility_primary_url"] = ""
        result.append(value)
    return result
