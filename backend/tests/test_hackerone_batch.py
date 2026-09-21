from types import SimpleNamespace

from app.hackerone_batch import reconcile_hackerone_batch
from app.hackerone_client import HackerOneClientError
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
    normalized = [
        {
            **member,
            "snapshot_sha256": str(member.get("snapshot_sha256") or ("a" * 64)),
        }
        for member in members
    ]
    return {
        "id": "batch-1",
        "provider": "hackerone",
        "mode": mode,
        "state": "running",
        "members": normalized,
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
    monkeypatch.setattr(
        "app.hackerone_client.fetch_hackerone_program_snapshot",
        lambda handle: SimpleNamespace(
            handle=handle,
            snapshot_sha256="a" * 64,
            program={"submission_state": "open", "state": "public_mode"},
        ),
    )

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



def test_sequential_batch_requires_review_when_remote_snapshot_changes(
    tmp_path,
    monkeypatch,
):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1", state="ready"))
    store.save_campaign(_campaign("c2", state="ready"))
    store.save_hackerone_batch(
        _batch(
            "sequential",
            [
                {
                    "index": 0,
                    "campaign_id": "c1",
                    "handle": "one",
                    "status": "ready",
                },
                {
                    "index": 1,
                    "campaign_id": "c2",
                    "handle": "two",
                    "status": "ready",
                },
            ],
        ),
        expected_version=0,
    )
    queue = FakeQueue({})
    started = []

    monkeypatch.setattr(
        "app.main.start_campaign",
        lambda campaign_id: started.append(campaign_id),
    )
    monkeypatch.setattr(
        "app.hackerone_client.fetch_hackerone_program_snapshot",
        lambda handle: SimpleNamespace(
            handle=handle,
            snapshot_sha256="b" * 64 if handle == "one" else "a" * 64,
            program={"submission_state": "open", "state": "public_mode"},
        ),
    )

    first = reconcile_hackerone_batch(queue, store, "batch-1")
    assert first is not None
    assert first["members"][0]["status"] == "review"
    assert first["members"][0]["reason"] == "remote_snapshot_changed_since_batch_admission"
    assert started == []

    second = reconcile_hackerone_batch(queue, store, "batch-1")
    assert second is not None
    assert second["members"][1]["status"] == "running"
    assert started == ["c2"]


def test_sequential_batch_requires_review_when_program_pauses(
    tmp_path,
    monkeypatch,
):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1", state="ready"))
    store.save_hackerone_batch(
        _batch(
            "sequential",
            [
                {
                    "index": 0,
                    "campaign_id": "c1",
                    "handle": "one",
                    "status": "ready",
                }
            ],
        ),
        expected_version=0,
    )
    queue = FakeQueue({})
    monkeypatch.setattr(
        "app.hackerone_client.fetch_hackerone_program_snapshot",
        lambda handle: SimpleNamespace(
            handle=handle,
            snapshot_sha256="a" * 64,
            program={"submission_state": "paused", "state": "public_mode"},
        ),
    )

    result = reconcile_hackerone_batch(queue, store, "batch-1")

    assert result is not None
    assert result["members"][0]["status"] == "review"
    assert result["members"][0]["reason"] == "remote_submissions_no_longer_open"
    assert result["state"] == "completed"


def test_sequential_batch_retries_after_transient_remote_revalidation_failure(
    tmp_path,
    monkeypatch,
):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(_campaign("c1", state="ready"))
    store.save_hackerone_batch(
        _batch(
            "sequential",
            [
                {
                    "index": 0,
                    "campaign_id": "c1",
                    "handle": "one",
                    "status": "ready",
                }
            ],
        ),
        expected_version=0,
    )
    queue = FakeQueue({})
    calls = {"count": 0}
    started = []

    def fetch(handle):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HackerOneClientError("temporary", status_code=503)
        return SimpleNamespace(
            handle=handle,
            snapshot_sha256="a" * 64,
            program={"submission_state": "open", "state": "public_mode"},
        )

    monkeypatch.setattr(
        "app.hackerone_client.fetch_hackerone_program_snapshot",
        fetch,
    )
    monkeypatch.setattr(
        "app.main.start_campaign",
        lambda campaign_id: started.append(campaign_id),
    )

    first = reconcile_hackerone_batch(queue, store, "batch-1")
    assert first is not None
    assert first["members"][0]["status"] == "ready"
    assert first["members"][0]["reason"] == "remote_revalidation_unavailable"
    assert started == []

    second = reconcile_hackerone_batch(queue, store, "batch-1")
    assert second is not None
    assert second["members"][0]["status"] == "running"
    assert started == ["c1"]
