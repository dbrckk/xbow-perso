from __future__ import annotations

from typing import Any


def build_program_discovery(
    *,
    programs: list[dict[str, Any]],
    review_profiles: list[dict[str, Any]],
    intelligence: dict[str, Any] | None,
    verified_snapshots: dict[str, str] | None = None,
    runtime: dict[str, Any] | None = None,
    catalog_changes: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Build a read-only discovery view for low-friction program selection."""
    verified = verified_snapshots or {}
    runtime = runtime or {}
    changes = catalog_changes or {}
    added = set(changes.get("added") or [])
    changed = set(changes.get("changed") or [])
    profiles_by_handle: dict[str, list[dict[str, Any]]] = {}
    for profile in review_profiles:
        handle = str(profile.get("handle") or "")
        if handle:
            profiles_by_handle.setdefault(handle, []).append(profile)

    program_signals = dict((intelligence or {}).get("program_signals") or {})
    items: list[dict[str, Any]] = []

    for program in programs:
        handle = str(program.get("handle") or "")
        profile_candidates = profiles_by_handle.get(handle, [])
        current_sha = str(verified.get(handle) or "")
        exact_profile = next(
            (
                profile for profile in profile_candidates
                if current_sha and str(profile.get("snapshot_sha256") or "") == current_sha
            ),
            None,
        )

        submission_open = str(program.get("submission_state") or "").lower() not in {
            "paused", "closed", "disabled"
        }
        state_open = str(program.get("state") or "").lower() not in {
            "closed", "disabled", "archived"
        }

        reasons: list[str] = []
        if not submission_open or not state_open:
            status = "BLOCKED"
            reasons.append("program_not_currently_open")
        elif exact_profile is not None:
            status = "READY"
            reasons.append("exact_review_profile_matches_current_snapshot")
        else:
            status = "REVIEW"
            if profile_candidates:
                reasons.append("saved_profile_requires_snapshot_revalidation")
            else:
                reasons.append("first_review_required")

        signal = dict(program_signals.get(handle) or {})
        score = 0
        if program.get("offers_bounties") is True:
            score += 25
        if program.get("gold_standard_safe_harbor") is True:
            score += 10
        if handle in added:
            score += 15
            reasons.append("new_program")
        elif handle in changed:
            score += 10
            reasons.append("catalog_changed")
        if exact_profile is not None:
            score += 20
        historical = float(signal.get("historical_value_score") or 0.0)
        score += min(25, int(historical))

        items.append({
            "handle": handle,
            "name": program.get("name") or handle,
            "status": status,
            "reasons": reasons,
            "offers_bounties": program.get("offers_bounties"),
            "gold_standard_safe_harbor": program.get("gold_standard_safe_harbor"),
            "submission_state": program.get("submission_state"),
            "state": program.get("state"),
            "priority_score": min(100, score),
            "historical_value_score": historical,
            "historical_usd_awarded_max": float(signal.get("usd_awarded_max") or 0.0),
            "top_categories": list(signal.get("top_categories") or [])[:4],
            "review_profile_available": bool(profile_candidates),
            "snapshot_verified": bool(current_sha),
            "exact_review_profile": exact_profile is not None,
            "runtime_recon_ready": bool(runtime.get("recon")),
            "runtime_scanner_ready": bool(runtime.get("scanner")),
            "automatic_launch": False,
            "scope_expansion": False,
        })

    items.sort(
        key=lambda item: (
            {"READY": 0, "REVIEW": 1, "BLOCKED": 2}[item["status"]],
            -int(item["priority_score"]),
            str(item["name"]).lower(),
        )
    )
    summary = {
        "total": len(items),
        "ready": sum(1 for item in items if item["status"] == "READY"),
        "review": sum(1 for item in items if item["status"] == "REVIEW"),
        "blocked": sum(1 for item in items if item["status"] == "BLOCKED"),
    }
    return {
        "summary": summary,
        "programs": items,
        "read_only": True,
        "automatic_launch": False,
        "scope_expansion": False,
        "historical_signals_are_advisory": True,
    }
