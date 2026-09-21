from app.hackerone_batch import reconcile_hackerone_batch, reconcile_hackerone_batches
from app.storage import Storage


class FakeQueue:
    def __init__(self, counts):
        self.counts = counts

    def campaign_job_status_counts(self, campaign_id):
        return {
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            **self.counts.get(campaign_id, {}),
        }


def _campaign(campaign_id, state="running"):
    return {
        "id": campaign_id,
        "state": state,
        "created_at": "2026-09-20T12:00:00+00:00",
        "updated_at": "2026-09-20T12:00:00+00:00",
    }


def _batch(mode, members):
    return {
        "id": "batch-1",
        "provider": "hackerone",
        "mode": mode,
        "state": "running",
        "members": members,
        "created_at": "2026-09-20T12:00:00+00:00",
        "updated_at": "2026-09-20T12:00:00+00:00",
    }


def test_sequential_batch_starts_next_member_after_previous_drains(
    tmp_path, monkeypatch
):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1"))
    store.save_campaign(_campaign("c2", state="ready"))
    store.save_hackerone_batch(
        _batch(
            "sequential",
            [
                {"index": 0, "campaign_id": "c1", "handle": "one", "status": "running"},
                {"index": 1, "campaign_id": "c2", "handle": "two", "status": "ready"},
            ],
        ),
        expected_version=0,
    )
    queue = FakeQueue({"c1": {"completed": 2}})
    started = []

    def fake_start(campaign_id):
        started.append(campaign_id)
        return {"campaign_id": campaign_id}

    monkeypatch.setattr("app.main.start_campaign", fake_start)

    result = reconcile_hackerone_batch(queue, store, "batch-1")

    assert result is not None
    assert started == ["c2"]
    assert [member["status"] for member in result["members"]] == ["done", "running"]
    assert result["state"] == "running"


def test_parallel_batch_finishes_after_all_members_drain(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    for campaign_id in ("c1", "c2"):
        store.save_campaign(_campaign(campaign_id))
    store.save_hackerone_batch(
        _batch(
            "parallel",
            [
                {"index": 0, "campaign_id": "c1", "handle": "one", "status": "running"},
                {"index": 1, "campaign_id": "c2", "handle": "two", "status": "running"},
            ],
        ),
        expected_version=0,
    )
    queue = FakeQueue(
        {
            "c1": {"completed": 1},
            "c2": {"completed": 3},
        }
    )

    result = reconcile_hackerone_batch(queue, store, "batch-1")

    assert result is not None
    assert result["state"] == "completed"
    assert result["summary"]["done"] == 2


def test_batch_waits_while_member_has_active_jobs(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1"))
    original = _batch(
        "sequential",
        [{"index": 0, "campaign_id": "c1", "handle": "one", "status": "running"}],
    )
    store.save_hackerone_batch(original, expected_version=0)
    queue = FakeQueue({"c1": {"queued": 1, "completed": 1}})

    result = reconcile_hackerone_batch(queue, store, "batch-1")

    assert result is not None
    assert result["members"][0]["status"] == "running"
    assert result["state"] == "running"



def test_parallel_batch_recovers_ready_members_after_restart(tmp_path, monkeypatch):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1", state="ready"))
    store.save_campaign(_campaign("c2", state="ready"))
    store.save_hackerone_batch(
        _batch(
            "parallel",
            [
                {"index": 0, "campaign_id": "c1", "handle": "one", "status": "ready"},
                {"index": 1, "campaign_id": "c2", "handle": "two", "status": "ready"},
            ],
        ),
        expected_version=0,
    )
    queue = FakeQueue({})
    started = []

    def fake_start(campaign_id):
        started.append(campaign_id)
        raw, version = store.get_campaign_record(campaign_id)
        raw["state"] = "running"
        store.save_campaign(raw, expected_version=version)
        return {"campaign_id": campaign_id}

    monkeypatch.setattr("app.main.start_campaign", fake_start)

    result = reconcile_hackerone_batch(queue, store, "batch-1")

    assert result is not None
    assert started == ["c1", "c2"]
    assert [member["status"] for member in result["members"]] == ["running", "running"]
    assert result["state"] == "running"


def test_parallel_start_conflict_reconciles_existing_running_campaign(
    tmp_path, monkeypatch
):
    from fastapi import HTTPException

    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1", state="running"))
    store.save_hackerone_batch(
        _batch(
            "parallel",
            [{"index": 0, "campaign_id": "c1", "handle": "one", "status": "ready"}],
        ),
        expected_version=0,
    )
    queue = FakeQueue({})

    def fake_start(_campaign_id):
        raise HTTPException(status_code=409, detail="Cannot start from running")

    monkeypatch.setattr("app.main.start_campaign", fake_start)

    result = reconcile_hackerone_batch(queue, store, "batch-1")

    assert result is not None
    assert result["members"][0]["status"] == "running"
    assert result["members"][0].get("reason") is None
    assert result["state"] == "running"


def test_parallel_start_conflict_on_ready_campaign_is_retried_not_blocked(
    tmp_path, monkeypatch
):
    from fastapi import HTTPException

    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1", state="ready"))
    store.save_hackerone_batch(
        _batch(
            "parallel",
            [{"index": 0, "campaign_id": "c1", "handle": "one", "status": "ready"}],
        ),
        expected_version=0,
    )
    queue = FakeQueue({})

    def fake_start(_campaign_id):
        raise HTTPException(status_code=409, detail="conflict")

    monkeypatch.setattr("app.main.start_campaign", fake_start)

    result = reconcile_hackerone_batch(queue, store, "batch-1")

    assert result is not None
    assert result["members"][0]["status"] == "ready"
    assert result["members"][0]["reason"] == "start_conflict_retry"
    assert result["state"] == "queued"



def test_active_batch_reconcile_is_not_starved_by_newer_completed_batches(
    tmp_path, monkeypatch
):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("active-campaign", state="ready"))
    active = {
        "id": "active-old",
        "provider": "hackerone",
        "mode": "sequential",
        "state": "queued",
        "members": [
            {
                "index": 0,
                "campaign_id": "active-campaign",
                "handle": "active",
                "status": "ready",
            }
        ],
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    store.save_hackerone_batch(active, expected_version=0)

    for index in range(25):
        finished = {
            "id": f"done-{index}",
            "provider": "hackerone",
            "mode": "sequential",
            "state": "completed",
            "members": [
                {
                    "index": 0,
                    "campaign_id": f"done-campaign-{index}",
                    "handle": f"done-{index}",
                    "status": "done",
                }
            ],
            "created_at": f"2026-09-20T{index % 24:02d}:00:00+00:00",
            "updated_at": f"2026-09-20T{index % 24:02d}:30:00+00:00",
        }
        store.save_hackerone_batch(finished, expected_version=0)

    started = []

    def fake_start(campaign_id):
        started.append(campaign_id)
        raw, version = store.get_campaign_record(campaign_id)
        raw["state"] = "running"
        store.save_campaign(raw, expected_version=version)
        return {"campaign_id": campaign_id}

    monkeypatch.setattr("app.main.start_campaign", fake_start)

    reconciled = reconcile_hackerone_batches(FakeQueue({}), store, limit=20)

    assert reconciled == 1
    assert started == ["active-campaign"]
    updated = store.get_hackerone_batch("active-old")
    assert updated["members"][0]["status"] == "running"
    assert updated["state"] == "running"


def test_active_batch_listing_prefers_oldest_active_work(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    for batch_id, updated_at in (
        ("newer", "2026-09-20T12:00:00+00:00"),
        ("older", "2026-09-19T12:00:00+00:00"),
    ):
        store.save_hackerone_batch(
            {
                "id": batch_id,
                "provider": "hackerone",
                "mode": "sequential",
                "state": "queued",
                "members": [
                    {
                        "index": 0,
                        "campaign_id": batch_id + "-campaign",
                        "handle": batch_id,
                        "status": "ready",
                    }
                ],
                "created_at": updated_at,
                "updated_at": updated_at,
            },
            expected_version=0,
        )

    active = store.list_active_hackerone_batches(limit=2)

    assert [item["id"] for item in active] == ["older", "newer"]
