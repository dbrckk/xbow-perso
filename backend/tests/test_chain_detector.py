from app.chain_detector import detect_chains
from app.observation_graph import Observation, ObservationGraph


def test_complete_validation_chain_is_prioritized():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(Observation("v1", "validation", "observed", "validator", parent_ids=("f1",)))
    graph.add(
        Observation(
            "e1",
            "evidence",
            "artifact-1",
            "validator",
            parent_ids=("v1",),
            metadata={"artifact_kind": "validation"},
        )
    )
    graph.add(Observation("a2", "asset", "other.test", "recon"))

    chains = detect_chains(graph)

    assert chains[0].complete_validation_chain is True
    assert chains[0].node_ids == ("a1", "f1", "v1", "e1")
    assert chains[0].terminal_kind == "evidence"


def test_chain_detection_is_deterministic_and_bounded():
    graph = ObservationGraph()
    for index in range(4):
        graph.add(Observation(f"a{index}", "asset", f"host-{index}.test", "recon"))

    first = detect_chains(graph, limit=2)
    second = detect_chains(graph, limit=2)

    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert len(first) == 2


def test_max_depth_truncates_long_provenance_path():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("e1", "endpoint", "https://example.test", "recon", parent_ids=("a1",)))
    graph.add(Observation("f1", "finding", "f1", "scanner", parent_ids=("e1",)))

    chains = detect_chains(graph, max_depth=2)

    assert chains[0].node_ids == ("a1", "e1")
    assert chains[0].complete_validation_chain is False


def test_invalid_bounds_fail_closed():
    graph = ObservationGraph()

    for kwargs in ({"max_depth": 0}, {"max_depth": 33}, {"limit": 0}, {"limit": 201}):
        try:
            detect_chains(graph, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid chain bounds should fail")
