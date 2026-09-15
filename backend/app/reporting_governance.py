from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .observation_graph import ObservationGraph
from .report_provenance import (
    ReportProvenance,
    aggregate_report_provenance_fingerprint,
    build_report_provenance,
)
from .report_quality import ReportQualityGate, build_report_quality_gates
from .report_readiness import ReportReadiness, build_report_readiness


@dataclass(frozen=True)
class ReportingGovernanceSnapshot:
    readiness: tuple[ReportReadiness, ...]
    provenance: tuple[ReportProvenance, ...]
    quality_gates: tuple[ReportQualityGate, ...]
    provenance_fingerprint: str
    governance_fingerprint: str

    def summary(self) -> dict[str, Any]:
        return {
            "findings": len(self.readiness),
            "submission_ready": sum(
                item.submission_ready for item in self.quality_gates
            ),
            "provenance_complete": sum(
                item.complete for item in self.provenance
            ),
            "quality_high": sum(
                item.grade in {"A", "B"} for item in self.quality_gates
            ),
            "provenance_fingerprint": self.provenance_fingerprint,
            "governance_fingerprint": self.governance_fingerprint,
            "read_only": True,
            "advisory_only": True,
        }


REPORTING_GOVERNANCE_SCHEMA = "reporting-governance-v1"


def reporting_governance_document(
    readiness: tuple[ReportReadiness, ...],
    provenance: tuple[ReportProvenance, ...],
    quality_gates: tuple[ReportQualityGate, ...],
    provenance_fingerprint: str,
) -> dict[str, Any]:
    return {
        "schema": REPORTING_GOVERNANCE_SCHEMA,
        "provenance_fingerprint": provenance_fingerprint,
        "readiness": [
            item.to_dict()
            for item in sorted(readiness, key=lambda item: item.finding_id)
        ],
        "provenance": [
            item.to_dict()
            for item in sorted(provenance, key=lambda item: item.finding_id)
        ],
        "quality_gates": [
            item.to_dict()
            for item in sorted(quality_gates, key=lambda item: item.finding_id)
        ],
    }


def reporting_governance_fingerprint(
    document: dict[str, Any],
) -> str:
    encoded = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_reporting_governance_snapshot(
    snapshot: ReportingGovernanceSnapshot,
) -> dict[str, Any]:
    document = reporting_governance_document(
        snapshot.readiness,
        snapshot.provenance,
        snapshot.quality_gates,
        snapshot.provenance_fingerprint,
    )
    computed = reporting_governance_fingerprint(document)
    return {
        "valid": computed == snapshot.governance_fingerprint,
        "schema": REPORTING_GOVERNANCE_SCHEMA,
        "expected_fingerprint": snapshot.governance_fingerprint,
        "computed_fingerprint": computed,
        "read_only": True,
        "automatic_mutation": False,
    }


def build_reporting_governance_snapshot(
    findings: list[Any],
    graph: ObservationGraph,
) -> ReportingGovernanceSnapshot:
    readiness = tuple(build_report_readiness(findings, graph))
    provenance = tuple(
        build_report_provenance(
            [str(item.id) for item in findings],
            graph,
        )
    )
    quality_gates = tuple(
        build_report_quality_gates(
            list(readiness),
            list(provenance),
        )
    )
    provenance_fingerprint = aggregate_report_provenance_fingerprint(
        list(provenance)
    )
    document = reporting_governance_document(
        readiness,
        provenance,
        quality_gates,
        provenance_fingerprint,
    )
    return ReportingGovernanceSnapshot(
        readiness=readiness,
        provenance=provenance,
        quality_gates=quality_gates,
        provenance_fingerprint=provenance_fingerprint,
        governance_fingerprint=reporting_governance_fingerprint(document),
    )



def assess_report_artifact_freshness(
    *,
    artifact_id: str,
    generated_governance_fingerprint: str | None,
    generated_provenance_fingerprint: str | None,
    current: ReportingGovernanceSnapshot,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not generated_governance_fingerprint:
        reasons.append("missing_generated_governance_fingerprint")
    elif generated_governance_fingerprint != current.governance_fingerprint:
        reasons.append("reporting_governance_changed")
    if not generated_provenance_fingerprint:
        reasons.append("missing_generated_provenance_fingerprint")
    elif generated_provenance_fingerprint != current.provenance_fingerprint:
        reasons.append("report_provenance_changed")
    return {
        "schema": "report-artifact-freshness-v1",
        "artifact_id": artifact_id,
        "fresh": not reasons,
        "stale": bool(reasons),
        "stale_reasons": reasons,
        "generated_governance_fingerprint": generated_governance_fingerprint,
        "current_governance_fingerprint": current.governance_fingerprint,
        "generated_provenance_fingerprint": generated_provenance_fingerprint,
        "current_provenance_fingerprint": current.provenance_fingerprint,
        "read_only": True,
        "automatic_mutation": False,
    }
