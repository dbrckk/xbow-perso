from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


CVE_VALIDATION_PLAN_SCHEMA = "cve-validation-plan-v1"


@dataclass(frozen=True)
class CveValidationPlan:
    schema: str
    finding_id: str
    validation_mode: str
    recommended_checks: tuple[str, ...]
    destructive_testing_allowed: bool
    state_changing_validation_allowed: bool
    exploit_execution_allowed: bool
    automatic_execution_authorized: bool
    independent_validation_required: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recommended_checks"] = list(self.recommended_checks)
        return payload


def build_cve_validation_plan(
    finding: Any,
    *,
    verdict: Any,
) -> CveValidationPlan:
    finding_id = str(getattr(finding, "id", ""))
    verdict_name = str(getattr(verdict, "verdict", ""))
    behavioral = bool(getattr(verdict, "behavioral_evidence", False))
    version = bool(getattr(verdict, "version_evidence", False))
    high_version = bool(
        getattr(verdict, "high_confidence_version_evidence", False)
    )
    ambiguity = tuple(getattr(verdict, "ambiguity_reasons", ()) or ())

    if ambiguity:
        mode = "passive_recheck"
        checks = (
            "re_fingerprint_product_and_version",
            "check_package_or_build_metadata",
            "compare_behavior_against_known_safe_baseline",
        )
    elif verdict_name == "behaviorally_supported_cve_candidate" and high_version:
        mode = "safe_active"
        checks = (
            "reproduce_non_destructive_behavior",
            "capture_request_response_digests",
            "independent_validator_recheck",
        )
    elif high_version or version:
        mode = "safe_active"
        checks = (
            "verify_exact_product_and_version",
            "run_non_destructive_template_validation",
            "capture_request_response_digests",
        )
    elif verdict_name == "identifier_only_candidate":
        mode = "passive_recheck"
        checks = (
            "verify_cve_metadata",
            "verify_product_identity",
            "verify_version_evidence",
        )
    elif behavioral:
        mode = "passive_recheck"
        checks = (
            "compare_behavior_against_known_safe_baseline",
            "independent_validator_recheck",
        )
    else:
        mode = "defer"
        checks = ("collect_more_evidence",)

    return CveValidationPlan(
        schema=CVE_VALIDATION_PLAN_SCHEMA,
        finding_id=finding_id,
        validation_mode=mode,
        recommended_checks=checks,
        destructive_testing_allowed=False,
        state_changing_validation_allowed=False,
        exploit_execution_allowed=False,
        automatic_execution_authorized=False,
        independent_validation_required=True,
    )
