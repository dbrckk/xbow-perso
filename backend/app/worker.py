from __future__ import annotations

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


class WorkerPolicyError(RuntimeError):
    pass


def build_strix_plan(campaign: Campaign, output_dir: str = "/data/strix_runs") -> WorkerPlan:
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
    active_enabled = os.getenv("XBOW_ENABLE_ACTIVE_SCANS", "false").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true" or not active_enabled
    return WorkerPlan(engine="strix", command=cmd, target=target, dry_run=dry_run, output_dir=output_dir)


def _bounded_timeout() -> int:
    timeout = int(os.getenv("WORKER_TIMEOUT_SECONDS", "7200"))
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
        }
    return {
        "engine": plan.engine,
        "status": "completed" if result.returncode in {0, 2} else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout[-20000:],
        "stderr": result.stderr[-20000:],
        "output_dir": str(output),
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
    limit = int(os.getenv("XBOW_MAX_STRIX_JSON_BYTES", str(5 * 1024 * 1024)))
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

        findings.append(
            Finding(
                title=str(item.get("title") or item.get("name") or "Strix finding"),
                severity=severity,
                asset=asset,
                endpoint=_optional_str(item.get("endpoint")),
                summary=str(item.get("summary") or item.get("description") or item.get("technical_analysis") or ""),
                evidence=[str(x) for x in evidence][:50],
                reproduction_steps=[str(x) for x in steps][:50],
                impact=str(item.get("impact") or ""),
                remediation=str(item.get("remediation") or item.get("recommendation") or ""),
                cwe=_optional_str(cwe),
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
