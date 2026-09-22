from __future__ import annotations

from typing import Any


def review_draft_blockers(draft: dict[str, Any]) -> list[str]:
    evidence = dict(draft.get("evidence") or {})
    blockers: list[str] = []
    if not str((draft.get("prefill") or {}).get("primary_url") or "").strip():
        blockers.append("no_compatible_primary_domain")
    if evidence.get("scope_complete") is not True:
        blockers.append("scope_incomplete_for_web_engine")
    if evidence.get("offers_bounties") is not True:
        blockers.append("bounties_not_offered")
    if evidence.get("policy_text_available") is not True:
        blockers.append("policy_text_unavailable")
    if list(draft.get("scope_exclusions") or []):
        blockers.append("scope_exclusions_require_manual_enforcement")
    if str(evidence.get("submission_state") or "").strip().lower() in {"closed", "paused", "disabled"}:
        blockers.append("submissions_not_open")
    if str(evidence.get("program_state") or "").strip().lower() in {"closed", "disabled", "archived"}:
        blockers.append("program_not_open")
    return blockers


def review_draft_is_usable(draft: dict[str, Any]) -> bool:
    return not review_draft_blockers(draft)


def build_hackerone_review_draft(snapshot) -> dict[str, Any]:
    """Build conservative first-review defaults from a verified HackerOne snapshot."""
    program = dict(snapshot.program or {})
    preview = dict(snapshot.preview or {})

    primary_url = None
    for asset in list(preview.get("assets") or []):
        if not isinstance(asset, dict):
            continue
        if asset.get("eligible_for_submission") is not True:
            continue
        if asset.get("compatible") is not True:
            continue
        if str(asset.get("asset_type") or "") != "Domain":
            continue
        identifier = str(asset.get("identifier") or "").strip().rstrip(".").lower()
        if identifier and "*" not in identifier:
            primary_url = f"https://{identifier}"
            break

    handle = str(snapshot.handle)
    snapshot_sha = str(snapshot.snapshot_sha256)
    draft = {
        "provider": "hackerone",
        "handle": handle,
        "snapshot_sha256": snapshot_sha,
        "prefill": {
            "name": str(program.get("name") or f"H1 {handle}")[:120],
            "primary_url": primary_url,
            "scope_document": snapshot.document,
            "authorization_reference": f"https://hackerone.com/{handle}",
            "policy_version": f"snapshot:{snapshot_sha[:16]}",
        },
        "policy_text": str(program.get("policy") or "")[:20000],
        "scope_exclusions": [
            {
                "category": str((item.get("attributes") or {}).get("category") or ""),
                "details": str((item.get("attributes") or {}).get("details") or "")[:4000],
            }
            for item in list(getattr(snapshot, "scope_exclusions", ()) or ())
            if isinstance(item, dict)
        ],
        "evidence": {
            "gold_standard_safe_harbor": program.get("gold_standard_safe_harbor"),
            "offers_bounties": program.get("offers_bounties"),
            "submission_state": program.get("submission_state"),
            "program_state": program.get("state"),
            "policy_text_available": bool(str(program.get("policy") or "").strip()),
            "scope_complete": bool(preview.get("complete")),
        },
        "manual_required": [
            "reviewed_by",
            "safe_harbor_confirmed",
            "automated_scanning",
            "max_requests_per_second",
            "test_account_required",
            "test_account_constraints_if_required",
            "additional_restrictions",
        ],
        "review_blockers": [],
        "automatic_confirmation": False,
        "automatic_launch": False,
        "scope_expansion": False,
    }

    draft["review_blockers"] = review_draft_blockers(draft)
    return draft