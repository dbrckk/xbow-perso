from pathlib import Path

from app.jobqueue import JobQueue


def test_queue_health_reports_integrity_without_payloads(tmp_path):
    q = JobQueue(str(tmp_path / "q.sqlite3"))
    q.enqueue("campaign-1", "report", {"secret": "must-not-leak"})

    health = q.health()

    assert health == {
        "ok": True,
        "storage": "sqlite",
        "integrity": "ok",
        "jobs": 1,
    }
    assert "secret" not in str(health)
    assert "must-not-leak" not in str(health)


def test_queue_health_fails_closed_on_corrupt_database(tmp_path):
    path = tmp_path / "q.sqlite3"
    q = JobQueue(str(path))
    Path(path).write_bytes(b"not-a-sqlite-database")

    health = q.health()

    assert health["ok"] is False
    assert health["storage"] == "sqlite"
    assert health["error"] == "DatabaseError"
