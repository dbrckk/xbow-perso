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
    done = q.finish(created["id"], "worker-a", True)
    assert done is not None
    assert done["status"] == "completed"
    assert done["claimed_by"] is None
    assert done["claimed_at"] is None


def test_failure_requeues_then_fails(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "independent_validation", {"finding_id": "f1"}, max_attempts=2)
    q.claim("worker-a")
    requeued = q.finish(job["id"], "worker-a", False, "transient")
    assert requeued is not None
    assert requeued["status"] == "queued"
    q.claim("worker-b")
    failed = q.finish(job["id"], "worker-b", False, "still broken")
    assert failed is not None
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


def test_stats_expose_counts_without_payloads(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    first = q.enqueue("campaign-1", "strix_scan", {"secret": "must-not-leak"})
    q.enqueue("campaign-2", "report", {"campaign_id": "campaign-2"})
    q.claim("worker-a")
    q.finish(first["id"], "worker-a", True)

    stats = q.stats()
    assert stats["total"] == 2
    assert stats["by_status"]["completed"] == 1
    assert stats["by_status"]["queued"] == 1
    assert stats["oldest_queued_at"] is not None
    assert "secret" not in str(stats)
    assert "must-not-leak" not in str(stats)


def test_heartbeat_renews_only_current_owner(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"})
    q.claim("worker-a")
    with q.connect() as db:
        db.execute(
            "UPDATE jobs SET claimed_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job["id"],),
        )

    assert q.heartbeat(job["id"], "worker-b") is False
    assert q.get(job["id"])["claimed_at"] == "2000-01-01T00:00:00+00:00"
    assert q.heartbeat(job["id"], "worker-a") is True
    assert q.get(job["id"])["claimed_at"] != "2000-01-01T00:00:00+00:00"


def test_heartbeat_rejects_finished_job(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "report", {})
    q.claim("worker-a")
    q.finish(job["id"], "worker-a", True)
    assert q.heartbeat(job["id"], "worker-a") is False


def test_stale_worker_cannot_finish_reclaimed_job(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "report", {}, max_attempts=2)
    q.claim("worker-a")
    with q.connect() as db:
        db.execute(
            "UPDATE jobs SET claimed_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job["id"],),
        )

    reclaimed = q.claim("worker-b")
    assert reclaimed is not None
    assert reclaimed["claimed_by"] == "worker-b"
    assert q.finish(job["id"], "worker-a", True) is None

    current = q.get(job["id"])
    assert current is not None
    assert current["status"] == "running"
    assert current["claimed_by"] == "worker-b"
    completed = q.finish(job["id"], "worker-b", True)
    assert completed is not None
    assert completed["status"] == "completed"


def test_stats_remain_healthy_after_expired_lease_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    job = q.enqueue("campaign-1", "report", {}, max_attempts=2)
    q.claim("dead-worker")
    with q.connect() as db:
        db.execute(
            "UPDATE jobs SET claimed_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job["id"],),
        )

    assert q.recover_expired_leases() == 1
    stats = q.stats()
    assert stats["total"] == 1
    assert stats["by_status"]["queued"] == 1
    assert stats["by_status"]["running"] == 0
    assert stats["oldest_queued_at"] is not None
