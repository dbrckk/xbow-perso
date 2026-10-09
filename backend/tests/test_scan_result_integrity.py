from app.observation_graph import Observation, ObservationGraph
from app.scan_result_integrity import conflicting_scan_terminal_job_ids


def _event(graph, oid, job_id, status):
    graph.add(
        Observation(
            oid, "evidence", status, "nuclei",
            metadata={"phase": "scan", "status": status, "job_id": job_id},
        )
    )


def test_completed_failed_same_job_is_terminal_contradiction():
    graph = ObservationGraph()
    _event(graph, "scan:done", "job-1", "completed")
    _event(graph, "scan:failed", "job-1", "failed")
    assert conflicting_scan_terminal_job_ids(graph) == frozenset({"job-1"})


def test_completed_and_queued_same_job_is_not_terminal_contradiction():
    graph = ObservationGraph()
    _event(graph, "scan:queued", "job-1", "queued")
    _event(graph, "scan:done", "job-1", "completed")
    assert conflicting_scan_terminal_job_ids(graph) == frozenset()


def test_separate_job_ids_do_not_conflict():
    graph = ObservationGraph()
    _event(graph, "scan:done", "job-1", "completed")
    _event(graph, "scan:failed", "job-2", "failed")
    assert conflicting_scan_terminal_job_ids(graph) == frozenset()


def test_invalid_ids_cannot_invent_job_identity():
    graph = ObservationGraph()
    _event(graph, "scan:done", "", "completed")
    _event(graph, "scan:failed", "", "failed")
    _event(graph, "scan:done2", "x" * 129, "completed")
    _event(graph, "scan:failed2", "x" * 129, "failed")
    assert conflicting_scan_terminal_job_ids(graph) == frozenset()


def test_completed_and_cancelled_same_job_is_terminal_contradiction():
    graph = ObservationGraph()
    _event(graph, "scan:done", "job-1", "completed")
    _event(graph, "scan:cancelled", "job-1", "cancelled")
    assert conflicting_scan_terminal_job_ids(graph) == frozenset({"job-1"})


def test_scan_job_identity_rejects_invisible_and_control_characters():
    from app.scan_result_integrity import canonical_scan_job_id

    for invalid in ("", "   ", "job\x7f", "job\u200b", "job\n", "job\x00", 123, "x" * 129):
        assert canonical_scan_job_id(invalid) is None
    assert canonical_scan_job_id("  job-42  ") == "job-42"


def test_invisible_job_ids_cannot_invent_terminal_status_conflicts():
    graph = ObservationGraph()
    for index, job_id in enumerate(("job\x7f", "job\u200b")):
        _event(graph, f"scan:done:{index}", job_id, "completed")
        _event(graph, f"scan:failed:{index}", job_id, "failed")
    assert conflicting_scan_terminal_job_ids(graph) == frozenset()


def test_scanner_source_rejects_untrusted_identity_labels():
    from app.scan_result_integrity import canonical_scan_source

    for invalid in ("", "  ", "x" * 129, "nuclei\\nother", "nuclei\\x7f",
                    "nuclei\\u200b", "nuclei\\tother", 123):
        assert canonical_scan_source(invalid) is None
    assert canonical_scan_source("  nuclei  ") == "nuclei"
    assert canonical_scan_source("scanner v2") == "scanner v2"
