from app.jobqueue import JobQueue


def test_queue_claim_and_complete(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    created = q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"})
    assert created["status"] == "queued"
    claimed = q.claim("worker-a")
    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["attempts"] == 1
    assert q.claim("worker-b") is None
    done = q.finish(created["id"], True)
    assert done["status"] == "completed"


def test_failure_requeues_then_fails(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "independent_validation", {"finding_id": "f1"}, max_attempts=2)
    q.claim("worker-a")
    assert q.finish(job["id"], False, "transient")["status"] == "queued"
    q.claim("worker-b")
    failed = q.finish(job["id"], False, "still broken")
    assert failed["status"] == "failed"
    assert failed["last_error"] == "still broken"


def test_rejects_arbitrary_job_kind(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    try:
        q.enqueue("campaign-1", "shell", {"command": "anything"})
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("arbitrary job kinds must fail closed")
