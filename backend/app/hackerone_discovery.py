from __future__ import annotations

from typing import Any

from .opportunity_ranking import build_opportunity_signal
from .value_efficiency import build_value_efficiency_signal, select_diversified_portfolio


def build_program_discovery(
    *,
    programs: list[dict[str, Any]],
    review_profiles: list[dict[str, Any]],
    intelligence: dict[str, Any] | None,
    verified_snapshots: dict[str, str] | None = None,
    runtime: dict[str, Any] | None = None,
    catalog_changes: dict[str, list[str]] | None = None,
    local_outcomes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a read-only discovery view for low-friction program selection."""
    verified = verified_snapshots or {}
    runtime = runtime or {}
    changes = catalog_changes or {}
    local_outcomes = local_outcomes or {}
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
        local_signal = dict(local_outcomes.get(handle) or {})
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

        opportunity = build_opportunity_signal(
            status=status,
            program=program,
            signal=signal,
            runtime=runtime,
            is_new=handle in added,
            is_changed=handle in changed,
        )
        local_bonus = min(10, int(local_signal.get("local_outcome_score") or 0))
        if local_bonus:
            opportunity = {
                **opportunity,
                "opportunity_score": min(
                    100,
                    int(opportunity["opportunity_score"]) + local_bonus,
                ),
                "reasons": list(opportunity["reasons"]) + ["local_confirmed_outcome_signal"],
            }

        efficiency = build_value_efficiency_signal(
            status=status,
            opportunity_score=int(opportunity["opportunity_score"]),
            research_focus=list(opportunity["research_focus"]),
            runtime_ready_categories=list(opportunity["runtime_ready_categories"]),
            runtime_partial_categories=list(opportunity["runtime_partial_categories"]),
            gold_standard_safe_harbor=program.get("gold_standard_safe_harbor"),
        )

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
            "opportunity_score": opportunity["opportunity_score"],
            "opportunity_reasons": opportunity["reasons"],
            "research_focus": opportunity["research_focus"],
            "runtime_ready_categories": opportunity["runtime_ready_categories"],
            "runtime_partial_categories": opportunity["runtime_partial_categories"],
            "public_high_critical_density": opportunity["public_high_critical_density"],
            "value_efficiency_score": efficiency["value_efficiency_score"],
            "effort_factor": efficiency["effort_factor"],
            "efficiency_reasons": efficiency["efficiency_reasons"],
            "local_outcome_score": int(local_signal.get("local_outcome_score") or 0),
            "local_confirmed_findings": int(local_signal.get("confirmed_finding_count") or 0),
            "local_high_critical_confirmed": int(local_signal.get("high_critical_confirmed_count") or 0),
            "local_submitted_reports": int(local_signal.get("submitted_report_count") or 0),
            "local_smoothed_success_rate": float(local_signal.get("smoothed_success_rate") or 0.0),
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
            -int(item["value_efficiency_score"]),
            -int(item["opportunity_score"]),
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
        "recommended_portfolio": select_diversified_portfolio(
            items,
            limit=5,
            min_score=50,
        ),
        "read_only": True,
        "automatic_launch": False,
        "scope_expansion": False,
        "historical_signals_are_advisory": True,
    }
