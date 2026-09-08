from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from urllib.parse import urlparse

from .main import Campaign, is_host_allowed


@dataclass
class WorkerPlan:
    engine: str
    command: list[str]
    target: str
    dry_run: bool


class WorkerPolicyError(RuntimeError):
    pass


def build_strix_plan(campaign: Campaign) -> WorkerPlan:
    target = str(campaign.target.primary_url)
    host = (urlparse(target).hostname or "").lower()
    rules = campaign.target.rules
    if not is_host_allowed(host, rules.allowed_targets, rules.denied_targets):
        raise WorkerPolicyError("Target is outside declared scope")
    if not rules.automated_scanning:
        raise WorkerPolicyError("Automated scanning is disabled by program rules")

    cmd = ["strix", "--target", target]
    return WorkerPlan(
        engine="strix",
        command=cmd,
        target=target,
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
    )


def execute(plan: WorkerPlan) -> dict:
    if plan.dry_run:
        return {"engine": plan.engine, "status": "dry_run", "command": shlex.join(plan.command)}

    # Production deployments should execute this inside a dedicated worker
    # container/VM with egress filtering and resource limits.
    result = subprocess.run(
        plan.command,
        capture_output=True,
        text=True,
        timeout=int(os.getenv("WORKER_TIMEOUT_SECONDS", "7200")),
        check=False,
    )
    return {
        "engine": plan.engine,
        "status": "completed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout[-20000:],
        "stderr": result.stderr[-20000:],
    }
