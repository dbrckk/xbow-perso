from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .secret_vault import SecretVaultError, get_secret, vault_enabled
from .storage import CampaignConflictError


_MARKER_PREFIX = "xbow-runtime-learning-batch:"
_DEFAULT_REPO = "dbrckk/xbow-perso"
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class LearningSyncError(RuntimeError):
    pass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise LearningSyncError(f"{name} must be a boolean")


def _repo() -> str:
    value = (os.getenv("XBOW_GITHUB_LEARNING_REPO") or _DEFAULT_REPO).strip()
    if not _REPO_PATTERN.fullmatch(value):
        raise LearningSyncError("XBOW_GITHUB_LEARNING_REPO must be owner/repository")
    return value


def _token() -> str | None:
    if vault_enabled():
        try:
            value = get_secret("github_learning_token")
        except SecretVaultError:
            return None
        return value.strip() or None
    value = (os.getenv("XBOW_GITHUB_LEARNING_TOKEN") or "").strip()
    return value or None


def learning_sync_configuration() -> dict[str, Any]:
    enabled = _bool_env("XBOW_ENABLE_GITHUB_LEARNING_SYNC", True)
    repo = _repo()
    configured = bool(_token()) if enabled else False
    return {
        "enabled": enabled,
        "configured": configured,
        "repository": repo,
        "transport": "github_issue",
        "contains_secrets": False,
        "automatic_code_mutation": False,
    }


def _safe_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").replace(chr(0), "").split())
    return text[:limit]


def _campaign_digest(store, campaign_id: str) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id) if campaign_id else None
    if not campaign:
        return {
            "campaign_id": campaign_id,
            "state": "missing",
            "finding_count": 0,
            "confirmed_findings": 0,
            "severities": {},
            "statuses": {},
            "event_types": {},
            "finding_brief": [],
        }

    findings = list(campaign.get("findings") or [])
    events = list(campaign.get("events") or [])
    severity_counts = Counter(_safe_text(item.get("severity"), 32) or "unknown" for item in findings)
    status_counts = Counter(_safe_text(item.get("status"), 32) or "unknown" for item in findings)
    event_counts = Counter(_safe_text(item.get("type"), 80) or "unknown" for item in events)
    confirmed = [item for item in findings if str(item.get("status") or "") == "confirmed"]

    finding_brief = []
    for item in findings[:40]:
        finding_brief.append(
            {
                "severity": _safe_text(item.get("severity"), 32),
                "status": _safe_text(item.get("status"), 32),
                "cwe": _safe_text(item.get("cwe"), 40),
                "discovered_by": _safe_text(item.get("discovered_by"), 80),
                "validated_by": _safe_text(item.get("validated_by"), 80),
            }
        )

    return {
        "campaign_id": campaign_id,
        "state": _safe_text(campaign.get("state"), 32),
        "created_at": campaign.get("created_at"),
        "updated_at": campaign.get("updated_at"),
        "finding_count": len(findings),
        "confirmed_findings": len(confirmed),
        "severities": dict(sorted(severity_counts.items())),
        "statuses": dict(sorted(status_counts.items())),
        "event_types": dict(sorted(event_counts.items())),
        "finding_brief": finding_brief,
    }



def _learning_signals(members: list[dict[str, Any]]) -> dict[str, Any]:
    completed = 0
    blocked = 0
    confirmed_findings = 0
    finding_count = 0
    event_totals: Counter[str] = Counter()
    severity_totals: Counter[str] = Counter()
    status_totals: Counter[str] = Counter()
    cwe_totals: Counter[str] = Counter()
    recommendations: list[str] = []

    for member in members:
        campaign = dict(member.get("campaign") or {})
        state = str(campaign.get("state") or member.get("status") or "").lower()
        if state == "completed" or str(member.get("status") or "").lower() == "done":
            completed += 1
        if state in {"blocked", "failed", "cancelled"} or str(member.get("status") or "").lower() in {
            "blocked",
            "failed",
        }:
            blocked += 1

        confirmed_findings += int(campaign.get("confirmed_findings") or 0)
        finding_count += int(campaign.get("finding_count") or 0)
        event_totals.update(dict(campaign.get("event_types") or {}))
        severity_totals.update(dict(campaign.get("severities") or {}))
        status_totals.update(dict(campaign.get("statuses") or {}))
        for finding in list(campaign.get("finding_brief") or []):
            cwe = _safe_text(finding.get("cwe"), 40)
            if cwe:
                cwe_totals[cwe] += 1

    total = len(members)
    confirmation_rate = round(confirmed_findings / finding_count, 4) if finding_count else 0.0
    completion_rate = round(completed / total, 4) if total else 0.0

    if blocked:
        recommendations.append(
            "Inspect blocked or failed campaign reasons before increasing automation depth."
        )
    if event_totals.get("recon_task_completed", 0) == 0 and total:
        recommendations.append(
            "Recon completion is absent from this batch; verify reconnaissance worker coverage."
        )
    if finding_count and confirmed_findings == 0:
        recommendations.append(
            "Findings were produced without confirmation; prioritize validation quality and deduplication."
        )
    if confirmed_findings:
        recommendations.append(
            "Feed confirmed severity/CWE distributions into future portfolio and scanner prioritization."
        )
    if not recommendations:
        recommendations.append(
            "No obvious runtime bottleneck detected from sanitized batch telemetry."
        )

    return {
        "campaigns": {
            "total": total,
            "completed": completed,
            "blocked_or_failed": blocked,
            "completion_rate": completion_rate,
        },
        "findings": {
            "total": finding_count,
            "confirmed": confirmed_findings,
            "confirmation_rate": confirmation_rate,
            "severities": dict(sorted(severity_totals.items())),
            "statuses": dict(sorted(status_totals.items())),
            "cwes": dict(sorted(cwe_totals.items())),
        },
        "events": dict(sorted(event_totals.items())),
        "recommendations": recommendations[:8],
    }

def build_learning_digest(store, batch: dict[str, Any]) -> dict[str, Any]:
    members = []
    for member in list(batch.get("members") or []):
        campaign_id = str(member.get("campaign_id") or "")
        members.append(
            {
                "handle": _safe_text(member.get("handle"), 128),
                "status": _safe_text(member.get("status"), 32),
                "reason": _safe_text(member.get("reason"), 300),
                "campaign": _campaign_digest(store, campaign_id),
            }
        )

    return {
        "schema": "xbow-runtime-learning-v2",
        "batch_id": _safe_text(batch.get("id"), 128),
        "mode": _safe_text(batch.get("mode"), 32),
        "state": _safe_text(batch.get("state"), 32),
        "created_at": batch.get("created_at"),
        "updated_at": batch.get("updated_at"),
        "summary": dict(batch.get("summary") or {}),
        "members": members,
        "learning_signals": _learning_signals(members),
        "safety": {
            "reviewed_hackerone_profiles_only": True,
            "historical_awards_are_advisory_only": True,
            "raw_evidence_included": False,
            "request_bodies_included": False,
            "credentials_included": False,
            "automatic_code_mutation": False,
        },
    }


def _render_issue_body(digest: dict[str, Any]) -> str:
    lines = [
        f"<!-- {_MARKER_PREFIX}{digest['batch_id']} -->",
        "# XBOW runtime learning summary",
        "",
        f"- Batch: {digest['batch_id']}",
        f"- Mode: {digest['mode']}",
        f"- State: {digest['state']}",
        f"- Created: {digest.get('created_at') or '—'}",
        f"- Updated: {digest.get('updated_at') or '—'}",
        "",
        "## Batch outcome",
        "",
        json.dumps(digest.get("summary") or {}, ensure_ascii=False, sort_keys=True),
        "",
        "## Learning signals",
        "",
        json.dumps(digest.get("learning_signals") or {}, ensure_ascii=False, sort_keys=True, indent=2),
        "",
    ]
    for member in digest.get("members") or []:
        campaign = member.get("campaign") or {}
        lines.extend(
            [
                f"## {member.get('handle') or 'programme'}",
                "",
                f"- Batch status: {member.get('status') or '—'}",
                f"- Campaign state: {campaign.get('state') or '—'}",
                f"- Findings: {campaign.get('finding_count', 0)}",
                f"- Confirmed: {campaign.get('confirmed_findings', 0)}",
            ]
        )
        if member.get("reason"):
            lines.append(f"- Scheduler note: {member['reason']}")
        lines.extend(
            [
                "",
                "Severity distribution:",
                json.dumps(campaign.get("severities") or {}, ensure_ascii=False, sort_keys=True),
                "Finding status distribution:",
                json.dumps(campaign.get("statuses") or {}, ensure_ascii=False, sort_keys=True),
                "Execution event distribution:",
                json.dumps(campaign.get("event_types") or {}, ensure_ascii=False, sort_keys=True),
            ]
        )
        briefs = campaign.get("finding_brief") or []
        if briefs:
            lines.extend(["Finding brief (sanitized):", json.dumps(briefs, ensure_ascii=False, sort_keys=True, indent=2)])
        lines.append("")

    lines.extend(
        [
            "## Safety / learning contract",
            "",
            "- Generated from reviewed HackerOne program campaigns only.",
            "- Public historical bounty values are ranking signals only and never authorize targets.",
            "- Raw evidence, request bodies, credentials, tokens and reproduction payloads are excluded.",
            "- This issue is an input for future engineering analysis; it does not modify or merge code automatically.",
        ]
    )
    return "\n".join(lines)[:60000]


def _github_json(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "xbow-perso-learning-sync",
            "Content-Type": "application/json",
        },
    )
    timeout = float(os.getenv("XBOW_GITHUB_LEARNING_TIMEOUT_SECONDS", "10"))
    if not 2 <= timeout <= 30:
        raise LearningSyncError("XBOW_GITHUB_LEARNING_TIMEOUT_SECONDS must be between 2 and 30")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        raise LearningSyncError(f"github_http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LearningSyncError("github_unavailable") from exc
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LearningSyncError("github_invalid_response") from exc


def _existing_issue(repo: str, batch_id: str, token: str) -> dict[str, Any] | None:
    marker = f"{_MARKER_PREFIX}{batch_id}"
    query = urllib.parse.urlencode({"q": f'repo:{repo} is:issue "{marker}"', "per_page": 5})
    result = _github_json("GET", f"https://api.github.com/search/issues?{query}", token)
    for item in list((result or {}).get("items") or []):
        if marker in str(item.get("body") or ""):
            return item
    return None


def sync_batch_learning_issue(store, batch: dict[str, Any]) -> dict[str, Any]:
    config = learning_sync_configuration()
    if not config["enabled"]:
        return {"status": "disabled", "repository": config["repository"]}
    token = _token()
    if not token:
        return {"status": "unconfigured", "repository": config["repository"]}

    batch_id = str(batch.get("id") or "")
    if not batch_id:
        raise LearningSyncError("batch_id_missing")
    issue = _existing_issue(config["repository"], batch_id, token)
    if issue is None:
        digest = build_learning_digest(store, batch)
        issue = _github_json(
            "POST",
            f"https://api.github.com/repos/{config['repository']}/issues",
            token,
            {
                "title": f"[runtime-learning] Batch {batch_id}",
                "body": _render_issue_body(digest),
            },
        )

    number = int(issue.get("number") or 0)
    if number <= 0:
        raise LearningSyncError("github_issue_missing_number")
    return {
        "status": "synced",
        "repository": config["repository"],
        "issue_number": number,
        "issue_url": str(issue.get("html_url") or ""),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def _retry_due(record: dict[str, Any]) -> bool:
    attempted = str(record.get("attempted_at") or "")
    if not attempted:
        return True
    try:
        then = datetime.fromisoformat(attempted.replace("Z", "+00:00"))
    except ValueError:
        return True
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() >= 900


def sync_completed_learning_batches(store, *, limit: int = 20) -> int:
    config = learning_sync_configuration()
    if not config["enabled"] or not config["configured"]:
        return 0

    updated = 0
    for batch in store.list_hackerone_batches(limit=limit):
        if str(batch.get("state") or "") != "completed":
            continue
        current_sync = dict(batch.get("learning_repo_sync") or {})
        if current_sync.get("status") == "synced" or not _retry_due(current_sync):
            continue

        record = store.get_hackerone_batch_record(str(batch.get("id") or ""))
        if not record:
            continue
        current, version = record
        try:
            sync_record = sync_batch_learning_issue(store, current)
        except LearningSyncError as exc:
            sync_record = {
                "status": "error",
                "repository": config["repository"],
                "error": str(exc)[:160],
            }
        sync_record["attempted_at"] = datetime.now(timezone.utc).isoformat()
        next_batch = dict(current)
        next_batch["learning_repo_sync"] = sync_record
        next_batch["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            store.save_hackerone_batch(next_batch, expected_version=version)
        except CampaignConflictError:
            continue
        updated += 1
    return updated
