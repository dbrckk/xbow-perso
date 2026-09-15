from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .observation_graph import ObservationGraph


@dataclass(frozen=True)
class ReportProvenance:
    finding_id: str
    schema: str
    fingerprint: str
    finding_observation_id: str | None
    validation_observation_ids: tuple[str, ...]
    evidence_observation_ids: tuple[str, ...]
    evidence_artifact_ids: tuple[str, ...]
    source_classes: tuple[str, ...]
    complete: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "validation_observation_ids",
            "evidence_observation_ids",
            "evidence_artifact_ids",
            "source_classes",
            "blockers",
        ):
            payload[key] = list(payload[key])
        return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def aggregate_report_provenance_fingerprint(
    manifests: list[ReportProvenance],
) -> str:
    payload = [
        {
            "finding_id": item.finding_id,
            "fingerprint": item.fingerprint,
            "complete": item.complete,
        }
        for item in sorted(manifests, key=lambda item: item.finding_id)
    ]
    encoded = json.dumps(
        {
            "schema": "report-provenance-set-v1",
            "manifests": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_report_provenance(
    manifest: ReportProvenance | dict[str, Any],
) -> dict[str, Any]:
    payload = manifest.to_dict() if isinstance(manifest, ReportProvenance) else dict(manifest)
    expected = str(payload.get("fingerprint") or "")
    canonical = {
        "schema": payload.get("schema"),
        "finding_id": payload.get("finding_id"),
        "finding_observation_id": payload.get("finding_observation_id"),
        "validation_observation_ids": sorted(
            str(item) for item in (payload.get("validation_observation_ids") or [])
        ),
        "evidence_observation_ids": sorted(
            str(item) for item in (payload.get("evidence_observation_ids") or [])
        ),
        "evidence_artifact_ids": sorted(
            str(item) for item in (payload.get("evidence_artifact_ids") or [])
        ),
        "source_classes": sorted(
            str(item) for item in (payload.get("source_classes") or [])
        ),
    }
    computed = _fingerprint(canonical)
    schema_valid = canonical["schema"] == "report-provenance-v1"
    fingerprint_valid = bool(expected) and expected == computed
    return {
        "valid": schema_valid and fingerprint_valid,
        "schema_valid": schema_valid,
        "fingerprint_valid": fingerprint_valid,
        "expected_fingerprint": expected,
        "computed_fingerprint": computed,
        "read_only": True,
        "automatic_mutation": False,
    }


def build_report_provenance(
    finding_ids: list[str],
    graph: ObservationGraph,
) -> list[ReportProvenance]:
    items = {item.id: item for item in graph.values()}
    children: dict[str, list[Any]] = {}
    for item in graph.values():
        for parent_id in item.parent_ids:
            children.setdefault(parent_id, []).append(item)

    results: list[ReportProvenance] = []
    for raw_finding_id in finding_ids:
        finding_id = str(raw_finding_id)
        graph_id = f"finding:{finding_id}"
        finding = items.get(graph_id) or items.get(finding_id)
        blockers: list[str] = []

        if finding is None or finding.kind != "finding":
            blockers.append("finding_observation_missing")
            validations: list[Any] = []
        else:
            validations = [
                item
                for item in children.get(finding.id, [])
                if item.kind == "validation" and item.value == "observed"
            ]
            if not validations:
                blockers.append("validation_observation_missing")

        evidence = [
            item
            for validation in validations
            for item in children.get(validation.id, [])
            if item.kind == "evidence"
        ]
        if validations and not evidence:
            blockers.append("evidence_observation_missing")

        artifact_ids = sorted(
            {
                str(item.metadata.get("artifact_id"))
                for item in evidence
                if item.metadata.get("artifact_id")
            }
        )
        if evidence and not artifact_ids:
            blockers.append("evidence_artifact_reference_missing")

        validation_ids = tuple(sorted(item.id for item in validations))
        evidence_ids = tuple(sorted(item.id for item in evidence))
        source_classes = tuple(
            sorted(
                {
                    str(item.source)
                    for item in ([finding] if finding is not None else [])
                    + validations
                    + evidence
                }
            )
        )
        canonical = {
            "schema": "report-provenance-v1",
            "finding_id": finding_id,
            "finding_observation_id": finding.id if finding is not None else None,
            "validation_observation_ids": list(validation_ids),
            "evidence_observation_ids": list(evidence_ids),
            "evidence_artifact_ids": artifact_ids,
            "source_classes": list(source_classes),
        }
        results.append(
            ReportProvenance(
                finding_id=finding_id,
                schema="report-provenance-v1",
                fingerprint=_fingerprint(canonical),
                finding_observation_id=canonical["finding_observation_id"],
                validation_observation_ids=validation_ids,
                evidence_observation_ids=evidence_ids,
                evidence_artifact_ids=tuple(artifact_ids),
                source_classes=source_classes,
                complete=not blockers,
                blockers=tuple(sorted(set(blockers))),
            )
        )

    return sorted(results, key=lambda item: item.finding_id)
