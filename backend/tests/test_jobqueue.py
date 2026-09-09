from app.jobqueue import JobQueue


def test_queue_claim_and_complete(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    created = q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"})
    assert created["status"] == "queued"
    claimed = q.claim("worker-a")
    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["attempts"] == 1
    assert claimed["claimed_by"] == "worker-a"
    assert claimed["claimed_at"] is not None
    assert q.claim("worker-b") is None
    done = q.finish(created["id"], True)
    assert done["status"] == "completed"
    assert done["claimed_by"] is None
    assert done["claimed_at"] is None


def test_failure_requeues_then_fails(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "independent_validation", {"finding_id": "f1"}, max_attempts=2)
    q.claim("worker-a")
    assert q.finish(job["id"], False, "transient")["status"] == "queued"
    q.claim("worker-b")
    failed = q.finish(job["id"], False, "still broken")
    assert failed["status"] == "failed"
    assert failed["last_error"] == "still broken"


def test_expired_lease_requeues_abandoned_job(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"}, max_attempts=2)
    claimed = q.claim("dead-worker")
    assert claimed is not None
    with q.connect() as db:
        db.execute(
            "UPDATE jobs SET claimed_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job["id"],),
        )

    recovered = q.claim("replacement-worker")
    assert recovered is not None
    assert recovered["id"] == job["id"]
    assert recovered["status"] == "running"
    assert recovered["attempts"] == 2
    assert recovered["claimed_by"] == "replacement-worker"


def test_expired_lease_fails_when_retry_budget_exhausted(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "independent_validation", {"finding_id": "f1"}, max_attempts=1)
    q.claim("dead-worker")
    with q.connect() as db:
        db.execute(
            "UPDATE jobs SET claimed_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job["id"],),
        )

    assert q.recover_expired_leases() == 1
    failed = q.get(job["id"])
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["claimed_by"] is None
    assert failed["claimed_at"] is None
    assert failed["last_error"] == "worker lease expired before completion"


def test_invalid_lease_configuration_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "10")
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"})
    try:
        q.claim("worker-a")
    except ValueError as exc:
        assert "XBOW_JOB_LEASE_SECONDS" in str(exc)
    else:
        raise AssertionError("unsafe lease configuration must fail closed")


def test_rejects_arbitrary_job_kind(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    try:
        q.enqueue("campaign-1", "shell", {"command": "anything"})
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("arbitrary job kinds must fail closed")
