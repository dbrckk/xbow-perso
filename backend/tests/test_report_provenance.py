from app.observation_graph import Observation, ObservationGraph
from app.report_provenance import build_report_provenance


def _graph() -> ObservationGraph:
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:e1",
            "evidence",
            "artifact-reference",
            "independent-validator",
            parent_ids=("validation:v1",),
            metadata={"artifact_id": "artifact-f1"},
        )
    )
    return graph


def test_report_provenance_is_complete_and_deterministic():
    first = build_report_provenance(["f1"], _graph())[0]
    second = build_report_provenance(["f1"], _graph())[0]

    assert first.complete is True
    assert first.schema == "report-provenance-v1"
    assert first.finding_observation_id == "finding:f1"
    assert first.validation_observation_ids == ("validation:v1",)
    assert first.evidence_observation_ids == ("evidence:e1",)
    assert first.evidence_artifact_ids == ("artifact-f1",)
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64


def test_report_provenance_fails_closed_when_evidence_reference_is_missing():
    graph = ObservationGraph()
    graph.add(Observation("finding:f1", "finding", "f1", "scanner"))
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "validator",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:e1",
            "evidence",
            "artifact-reference",
            "validator",
            parent_ids=("validation:v1",),
        )
    )

    result = build_report_provenance(["f1"], graph)[0]

    assert result.complete is False
    assert "evidence_artifact_reference_missing" in result.blockers


def test_report_provenance_fails_closed_when_finding_is_missing():
    result = build_report_provenance(["missing"], ObservationGraph())[0]

    assert result.complete is False
    assert result.finding_observation_id is None
    assert "finding_observation_missing" in result.blockers
