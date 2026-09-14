from app.worker_service import _claim_for_role


class FakeQueue:
    def __init__(self):
        self.allowed = None
        self.generic_claimed = False

    def claim(self, worker_id):
        self.generic_claimed = True
        return {"worker_id": worker_id}

    def claim_allowed(self, worker_id, kinds):
        self.allowed = tuple(kinds)
        return {"worker_id": worker_id, "kinds": self.allowed}


def test_general_worker_keeps_scanner_preview_jobs_in_safe_mode(monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_ROLE", "general")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "false")
    monkeypatch.setenv("DRY_RUN", "true")
    queue = FakeQueue()

    _claim_for_role(queue, "worker-a")

    assert "nuclei_scan" in queue.allowed
    assert "strix_scan" in queue.allowed


def test_general_worker_excludes_scanner_jobs_for_active_execution(monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_ROLE", "general")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    queue = FakeQueue()

    _claim_for_role(queue, "worker-a")

    assert queue.allowed == (
        "independent_validation",
        "browser_flow",
        "recon_task",
        "report",
    )


def test_scanner_worker_claims_only_scanner_jobs(monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_ROLE", "scanner")
    queue = FakeQueue()

    _claim_for_role(queue, "worker-a")

    assert queue.allowed == ("nuclei_scan", "strix_scan")
