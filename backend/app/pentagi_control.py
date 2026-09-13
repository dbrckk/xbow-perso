from __future__ import annotations

import os
from dataclasses import dataclass, replace

from .main import Campaign
from .pentagi_adapter import PentagiFlowPlan, build_pentagi_flow_plan
from .pentagi_admission import PentagiAdmissionDecision, evaluate_pentagi_admission


class PentagiControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiControlPreview:
    plan: PentagiFlowPlan
    decision: PentagiAdmissionDecision
    operational_reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.decision.allowed and not self.operational_reasons


def _strict_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise PentagiControlError(f"{name} must be a boolean")


def prepare_pentagi_control_preview(campaign: Campaign) -> PentagiControlPreview:
    """Build the server-configured execution candidate and evaluate all API gates."""

    preview = build_pentagi_flow_plan(campaign)
    executable = replace(
        preview,
        dry_run=False,
        execution_supported=True,
    )
    decision = evaluate_pentagi_admission(campaign, executable)

    operational_reasons: list[str] = []
    if not _strict_bool_env("XBOW_ENABLE_PENTAGI_WORKER", False):
        operational_reasons.append("pentagi_worker_disabled")
    if not _strict_bool_env("XBOW_ENABLE_PENTAGI_TRANSPORT", False):
        operational_reasons.append("pentagi_transport_disabled")

    return PentagiControlPreview(
        plan=executable,
        decision=decision,
        operational_reasons=tuple(operational_reasons),
    )


def require_pentagi_control_ready(campaign: Campaign) -> PentagiControlPreview:
    preview = prepare_pentagi_control_preview(campaign)
    reasons = list(preview.decision.reasons) + list(preview.operational_reasons)
    if reasons:
        raise PentagiControlError(
            "PentAGI dispatch denied: " + ",".join(reasons)
        )
    return preview
