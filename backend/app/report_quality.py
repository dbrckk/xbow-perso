from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .report_provenance import ReportProvenance
from .report_readiness import ReportReadiness


@dataclass(frozen=True)
class ReportQualityGate:
    finding_id: str
    grade: str
    score: float
    human_review_ready: bool
    submission_ready: bool
    consensus_level: str
    evidence_quality_grade: str
    blockers: tuple[str, ...]
    checks: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


def build_report_quality_gates(
    readiness: list[ReportReadiness],
    provenance: list[ReportProvenance] | None = None,
) -> list[ReportQualityGate]:
    provenance_by_id = {
        item.finding_id: item for item in (provenance or [])
    }
    gates: list[ReportQualityGate] = []
    for item in readiness:
        provenance_item = provenance_by_id.get(item.finding_id)
        checks = {
            "human_review_ready": bool(item.ready_for_human_review),
            "submission_ready": bool(item.submission_ready),
            "evidence_high_quality": item.evidence_quality_grade == "high",
            "evidence_backed_validation": bool(
                item.evidence_backed_independent_validation
            ),
            "consensus_present": item.consensus_level
            in {"single_evidence_backed_validator", "quorum"},
            "metadata_complete": not item.metadata_blockers,
            "not_duplicate_candidate": not item.duplicate_candidate,
            "provenance_complete": bool(
                provenance_item and provenance_item.complete
            )
            if provenance is not None
            else True,
        }
        blockers = tuple(
            sorted(
                set(item.blockers)
                | set(item.metadata_blockers)
                | set(provenance_item.blockers if provenance_item else ())
                | {name for name, passed in checks.items() if not passed}
            )
        )
        score = round(sum(checks.values()) / len(checks), 4)

        if all(checks.values()) and item.consensus_level == "quorum":
            grade = "A"
        elif all(checks.values()):
            grade = "B"
        elif item.ready_for_human_review:
            grade = "C"
        else:
            grade = "D"

        gates.append(
            ReportQualityGate(
                finding_id=item.finding_id,
                grade=grade,
                score=score,
                human_review_ready=item.ready_for_human_review,
                submission_ready=item.submission_ready,
                consensus_level=item.consensus_level,
                evidence_quality_grade=item.evidence_quality_grade,
                blockers=blockers,
                checks=checks,
            )
        )

    return sorted(
        gates,
        key=lambda item: (
            {"D": 0, "C": 1, "B": 2, "A": 3}[item.grade],
            item.score,
            item.finding_id,
        ),
    )


def summarize_report_quality(
    gates: list[ReportQualityGate],
) -> dict[str, Any]:
    return {
        "total": len(gates),
        "by_grade": {
            grade: sum(item.grade == grade for item in gates)
            for grade in ("A", "B", "C", "D")
        },
        "submission_ready": sum(item.submission_ready for item in gates),
        "human_review_ready": sum(item.human_review_ready for item in gates),
        "average_score": round(
            sum(item.score for item in gates) / len(gates),
            4,
        )
        if gates
        else 0.0,
        "read_only": True,
        "advisory_only": True,
        "human_approval_required": True,
        "automatic_submission": False,
        "grade_semantics": {
            "A": "submission_complete_with_consensus_quorum",
            "B": "submission_complete_with_evidence_backed_consensus",
            "C": "human_review_ready_but_submission_incomplete",
            "D": "human_review_blocked",
        },
        "submission_gate": {
            "minimum_grade": "B",
            "requires_human_approval": True,
            "automatic_submission": False,
        },
    }
