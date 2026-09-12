from __future__ import annotations

import math
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .main import Campaign, Finding, is_host_allowed
from .scanner_registry import latest_scanner_artifact
from .strix_parser import StrixParserError, max_strix_json_bytes, parse_strix_json
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


def _safe_nuclei_output_dir(output_dir: str) -> str:
    root = Path(os.getenv("XBOW_NUCLEI_RUN_ROOT", "/data/nuclei_runs")).resolve()
    candidate = Path(output_dir)
    if candidate.is_symlink():
        raise WorkerPolicyError("Nuclei output directory must not be a symlink")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkerPolicyError("Nuclei output directory escaped configured run root") from exc
    return str(resolved)


def _nuclei_rate_limit(rps: float) -> tuple[int, str]:
    if rps <= 0:
        raise WorkerPolicyError("Nuclei rate limit must be positive")
    if rps < 1:
        seconds = max(1, int(math.ceil(1 / rps)))
        return 1, f"{seconds}s"
    return max(1, int(math.floor(rps))), "1s"


def build_nuclei_plan(campaign: Campaign, output_dir: str = "/data/nuclei_runs") -> WorkerPlan:
    output_dir = _safe_nuclei_output_dir(output_dir)
    target = str(campaign.target.primary_url)
    host = (urlparse(target).hostname or "").lower()
    rules = campaign.target.rules
    if not is_host_allowed(host, rules.allowed_targets, rules.denied_targets):
        raise WorkerPolicyError("Target is outside declared scope")
    if not rules.automated_scanning:
        raise WorkerPolicyError("Automated scanning is disabled by program rules")
    if rules.destructive_testing or rules.denial_of_service or rules.social_engineering or rules.credential_attacks:
        raise WorkerPolicyError("Unsafe campaign flags cannot be delegated to autonomous worker")

    active_enabled = _strict_bool_env("XBOW_ENABLE_ACTIVE_SCANS", False)
    nuclei_enabled = _strict_bool_env("XBOW_ENABLE_NUCLEI", False)
    dry_run_requested = _strict_bool_env("DRY_RUN", True)
    autonomous_cap = None
    if active_enabled and nuclei_enabled and not dry_run_requested:
        autonomous_cap = _max_autonomous_rps()
        if rules.max_requests_per_second > autonomous_cap:
            raise WorkerPolicyError(
                "Campaign request-rate limit exceeds autonomous worker admission cap"
            )
    dry_run = dry_run_requested or not active_enabled or not nuclei_enabled
    rate, duration = _nuclei_rate_limit(float(rules.max_requests_per_second))
    output_file = str(Path(output_dir) / "nuclei.jsonl")
    cmd = [
        "nuclei",
        "-target",
        target,
        "-type",
        "http",
        "-tags",
        "tech,misconfig,exposure",
        "-exclude-tags",
        "dos,fuzz",
        "-disable-unsigned-templates",
        "-no-interactsh",
        "-restrict-local-network-access",
        "-disable-redirects",
        "-no-stdin",
        "-silent",
        "-no-color",
        "-omit-raw",
        "-omit-template",
        "-rate-limit",
        str(rate),
        "-rate-limit-duration",
        duration,
        "-concurrency",
        "1",
        "-bulk-size",
        "1",
        "-payload-concurrency",
        "1",
        "-retries",
        "0",
        "-timeout",
        "10",
        "-disable-update-check",
        "-jsonl-export",
        output_file,
    ]
    return WorkerPlan(
        engine="nuclei",
        command=cmd,
        target=target,
        dry_run=dry_run,
        output_dir=output_dir,
        campaign_rps=float(rules.max_requests_per_second),
        admission_cap_rps=autonomous_cap,
    )


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

    timeout = _bounded_timeout()
    output = Path(plan.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            plan.command,
            cwd=output,
            capture_output=True,
            text=True,
            timeout=timeout,
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
    try:
        return max_strix_json_bytes()
    except StrixParserError as exc:
        raise WorkerPolicyError(str(exc)) from exc


def locate_vulnerabilities_json(output_dir: str) -> Path | None:
    candidate = latest_scanner_artifact("strix", output_dir)
    if candidate is None:
        return None
    if candidate.stat().st_size > _max_strix_json_bytes():
        return None
    return candidate


def parse_strix_vulnerabilities(path: str | Path, campaign: Campaign) -> list[Finding]:
    """Compatibility wrapper around the isolated Strix parser."""
    try:
        return parse_strix_json(path, campaign)
    except StrixParserError as exc:
        raise WorkerPolicyError(str(exc)) from exc


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

