from __future__ import annotations

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
            "read_only": True,
            "advisory_only": True,
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
    return ReportingGovernanceSnapshot(
        readiness=readiness,
        provenance=provenance,
        quality_gates=quality_gates,
        provenance_fingerprint=aggregate_report_provenance_fingerprint(
            list(provenance)
        ),
    )
