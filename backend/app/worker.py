from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .main import Campaign, Finding, is_host_allowed
from .storage import Storage


@dataclass
class WorkerPlan:
    engine: str
    command: list[str]
    target: str
    dry_run: bool
    output_dir: str
    campaign_rps: float
    admission_cap_rps: float | None


class WorkerPolicyError(RuntimeError):
    pass


def _strict_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise WorkerPolicyError(f"{name} must be a boolean")


def _safe_strix_output_dir(output_dir: str) -> str:
    root = Path(os.getenv("XBOW_STRIX_RUN_ROOT", "/data/strix_runs")).resolve()
    candidate = Path(output_dir)
    if candidate.is_symlink():
        raise WorkerPolicyError("Strix output directory must not be a symlink")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkerPolicyError("Strix output directory escaped configured run root") from exc
    return str(resolved)


def _max_autonomous_rps() -> float:
    try:
        limit = float(os.getenv("XBOW_MAX_AUTONOMOUS_RPS", "2.0"))
    except ValueError as exc:
        raise WorkerPolicyError("XBOW_MAX_AUTONOMOUS_RPS must be a number") from exc
    if not 0.1 <= limit <= 20.0:
        raise WorkerPolicyError("XBOW_MAX_AUTONOMOUS_RPS must be between 0.1 and 20")
    return limit


def build_strix_plan(campaign: Campaign, output_dir: str = "/data/strix_runs") -> WorkerPlan:
    output_dir = _safe_strix_output_dir(output_dir)
    target = str(campaign.target.primary_url)
    host = (urlparse(target).hostname or "").lower()
    rules = campaign.target.rules
    if not is_host_allowed(host, rules.allowed_targets, rules.denied_targets):
        raise WorkerPolicyError("Target is outside declared scope")
    if not rules.automated_scanning:
        raise WorkerPolicyError("Automated scanning is disabled by program rules")
    if rules.destructive_testing or rules.denial_of_service or rules.social_engineering or rules.credential_attacks:
        raise WorkerPolicyError("Unsafe campaign flags cannot be delegated to autonomous worker")

    cmd = ["strix", "-n", "--target", target]
    active_enabled = _strict_bool_env("XBOW_ENABLE_ACTIVE_SCANS", False)
    dry_run_requested = _strict_bool_env("DRY_RUN", True)
    autonomous_cap = None
    if active_enabled and not dry_run_requested:
        autonomous_cap = _max_autonomous_rps()
        if rules.max_requests_per_second > autonomous_cap:
            raise WorkerPolicyError(
                "Campaign request-rate limit exceeds autonomous worker admission cap"
            )
    dry_run = dry_run_requested or not active_enabled
    return WorkerPlan(
        engine="strix",
        command=cmd,
        target=target,
        dry_run=dry_run,
        output_dir=output_dir,
        campaign_rps=float(rules.max_requests_per_second),
        admission_cap_rps=autonomous_cap,
    )


def _bounded_timeout() -> int:
    raw = os.getenv("WORKER_TIMEOUT_SECONDS", "7200")
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise WorkerPolicyError("WORKER_TIMEOUT_SECONDS must be an integer") from exc
    if not 30 <= timeout <= 86400:
        raise WorkerPolicyError("WORKER_TIMEOUT_SECONDS must be between 30 and 86400")
    return timeout


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def execute(plan: WorkerPlan) -> dict:
    if plan.dry_run:
        return {
            "engine": plan.engine,
            "status": "dry_run",
            "command": shlex.join(plan.command),
            "reason": "active scanning requires DRY_RUN=false and XBOW_ENABLE_ACTIVE_SCANS=true",
            "campaign_rps": plan.campaign_rps,
            "admission_cap_rps": plan.admission_cap_rps,
        }

    output = Path(plan.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            plan.command,
            cwd=output,
            capture_output=True,
            text=True,
            timeout=_bounded_timeout(),
            check=False,
            env=_worker_env(),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "engine": plan.engine,
            "status": "timed_out",
            "returncode": None,
            "stdout": _text(exc.stdout)[-20000:],
            "stderr": _text(exc.stderr)[-20000:],
            "output_dir": str(output),
            "error": "worker execution timed out",
            "campaign_rps": plan.campaign_rps,
            "admission_cap_rps": plan.admission_cap_rps,
        }
    return {
        "engine": plan.engine,
        "status": "completed" if result.returncode in {0, 2} else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout[-20000:],
        "stderr": result.stderr[-20000:],
        "output_dir": str(output),
        "campaign_rps": plan.campaign_rps,
        "admission_cap_rps": plan.admission_cap_rps,
    }


def _worker_env() -> dict[str, str]:
    """Pass an explicit environment allowlist; never inherit arbitrary secrets."""
    allowed = {
        "PATH",
        "HOME",
        "STRIX_LLM",
        "LLM_API_KEY",
        "LLM_API_BASE",
        "STRIX_REASONING_EFFORT",
        "PERPLEXITY_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
    }
    return {k: v for k, v in os.environ.items() if k in allowed}


def _max_strix_json_bytes() -> int:
    raw = os.getenv("XBOW_MAX_STRIX_JSON_BYTES", str(5 * 1024 * 1024))
    try:
        limit = int(raw)
    except ValueError as exc:
        raise WorkerPolicyError("XBOW_MAX_STRIX_JSON_BYTES must be an integer") from exc
    if not 1024 <= limit <= 20 * 1024 * 1024:
        raise WorkerPolicyError("XBOW_MAX_STRIX_JSON_BYTES must be between 1 KiB and 20 MiB")
    return limit


def locate_vulnerabilities_json(output_dir: str) -> Path | None:
    root = Path(output_dir)
    if not root.exists():
        return None
    root_resolved = root.resolve()
    safe_matches: list[Path] = []
    for candidate in root.glob("**/vulnerabilities.json"):
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root_resolved)
        except (FileNotFoundError, ValueError, OSError):
            continue
        if not resolved.is_file() or resolved.stat().st_size > _max_strix_json_bytes():
            continue
        safe_matches.append(resolved)
    safe_matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return safe_matches[0] if safe_matches else None


def _finding_id(title: str, asset: str, endpoint: str | None, cwe: str | None, summary: str) -> str:
    """Stable identity makes retries idempotent without trusting scanner-provided IDs."""
    canonical = json.dumps(
        [title.strip(), asset.strip(), endpoint or "", cwe or "", summary.strip()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"strix-{digest[:32]}"


def parse_strix_vulnerabilities(path: str | Path, campaign: Campaign) -> list[Finding]:
    """Parse bounded Strix JSON artifacts into xbow-perso's canonical model."""
    path = Path(path)
    if path.stat().st_size > _max_strix_json_bytes():
        raise WorkerPolicyError("Strix vulnerabilities JSON exceeds configured size limit")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("vulnerabilities") or raw.get("findings") or raw.get("results") or []
    else:
        raise ValueError("unsupported Strix vulnerabilities JSON")
    if not isinstance(items, list):
        raise ValueError("Strix findings collection must be a list")

    findings: list[Finding] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        asset = str(item.get("asset") or item.get("target") or campaign.target.primary_url)
        host = (urlparse(asset).hostname or asset.split(":")[0]).lower()
        if not is_host_allowed(host, campaign.target.rules.allowed_targets, campaign.target.rules.denied_targets):
            continue
        severity = str(item.get("severity") or "info").lower()
        if severity not in {"info", "low", "medium", "high", "critical"}:
            severity = "info"
        steps = item.get("reproduction_steps") or item.get("poc_steps") or item.get("poc_description") or []
        if isinstance(steps, str):
            steps = [steps]
        evidence = item.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        cwe = item.get("cwe")
        if isinstance(cwe, list):
            cwe = ", ".join(str(x) for x in cwe)

        title = str(item.get("title") or item.get("name") or "Strix finding")
        endpoint = _optional_str(item.get("endpoint"))
        summary = str(item.get("summary") or item.get("description") or item.get("technical_analysis") or "")
        cwe_text = _optional_str(cwe)
        finding_id = _finding_id(title, asset, endpoint, cwe_text, summary)
        if finding_id in seen_ids:
            continue
        seen_ids.add(finding_id)

        findings.append(
            Finding(
                id=finding_id,
                title=title,
                severity=severity,
                asset=asset,
                endpoint=endpoint,
                summary=summary,
                evidence=[str(x) for x in evidence][:50],
                reproduction_steps=[str(x) for x in steps][:50],
                impact=str(item.get("impact") or ""),
                remediation=str(item.get("remediation") or item.get("recommendation") or ""),
                cwe=cwe_text,
                cvss=_optional_cvss(item.get("cvss")),
                status="validation_required",
                discovered_by="strix",
            )
        )
    return findings


def persist_execution_artifacts(store: Storage, campaign_id: str, result: dict) -> list[dict]:
    artifacts: list[dict] = []
    for key, kind in (("stdout", "scanner_stdout"), ("stderr", "scanner_stderr")):
        content = result.get(key)
        if content:
            artifacts.append(store.put_artifact(campaign_id, kind, str(content).encode(), media_type="text/plain"))
    vuln_path = locate_vulnerabilities_json(str(result.get("output_dir") or ""))
    if vuln_path:
        artifacts.append(
            store.put_artifact(
                campaign_id,
                "http_evidence",
                vuln_path.read_bytes(),
                media_type="application/json",
            )
        )
    return artifacts


def _optional_str(value) -> str | None:
    return None if value in {None, ""} else str(value)


def _optional_cvss(value) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 10 else None
