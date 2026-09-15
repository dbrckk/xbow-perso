import os
from uuid import uuid4

import pytest

from app.postgres_storage import PostgresStorage
from app.review_queue import persist_review_queue_snapshot
from app.storage import Storage


def _campaign(campaign_id: str) -> dict[str, str]:
    return {
        "id": campaign_id,
        "state": "ready",
        "created_at": "2026-09-15T00:00:00+00:00",
        "updated_at": "2026-09-15T00:00:00+00:00",
    }


def _snapshot(index: int) -> tuple[str, dict[str, object]]:
    fingerprint = f"{index:064x}"
    return fingerprint, {
        "schema": "review-queue-snapshot-v1",
        "fingerprint": fingerprint,
        "task_ids": [f"task-{index}"],
        "task_count": 1,
    }


def _assert_retention(store, campaign_id: str) -> None:
    store.save_campaign(_campaign(campaign_id))
    for index in range(3):
        _fingerprint, document = _snapshot(index)
        persist_review_queue_snapshot(
            store,
            campaign_id,
            document,
            retention_limit=2,
        )

    rows = store.list_review_queue_snapshots(campaign_id, limit=10)
    assert [row["fingerprint"] for row in rows] == [
        f"{2:064x}",
        f"{1:064x}",
    ]


def test_sqlite_review_queue_snapshot_retention_prunes_oldest(tmp_path):
    store = Storage(
        str(tmp_path / "db.sqlite3"),
        str(tmp_path / "artifacts"),
    )
    _assert_retention(store, "retention-sqlite")


def test_review_queue_snapshot_retention_is_campaign_scoped(tmp_path):
    store = Storage(
        str(tmp_path / "db.sqlite3"),
        str(tmp_path / "artifacts"),
    )
    _assert_retention(store, "retention-a")

    second_id = "retention-b"
    store.save_campaign(_campaign(second_id))
    fingerprint, document = _snapshot(9)
    persist_review_queue_snapshot(
        store,
        second_id,
        document,
        retention_limit=2,
    )

    assert len(store.list_review_queue_snapshots("retention-a", limit=10)) == 2
    assert [
        row["fingerprint"]
        for row in store.list_review_queue_snapshots(second_id, limit=10)
    ] == [fingerprint]


def test_review_queue_snapshot_retention_rejects_unsafe_bounds(tmp_path):
    store = Storage(
        str(tmp_path / "db.sqlite3"),
        str(tmp_path / "artifacts"),
    )
    store.save_campaign(_campaign("retention-bounds"))
    _fingerprint, document = _snapshot(1)

    for invalid in (0, 501):
        with pytest.raises(ValueError, match="between 1 and 500"):
            persist_review_queue_snapshot(
                store,
                "retention-bounds",
                document,
                retention_limit=invalid,
            )


POSTGRES_URL = os.getenv("XBOW_TEST_POSTGRES_URL")


@pytest.mark.skipif(
    not POSTGRES_URL,
    reason="XBOW_TEST_POSTGRES_URL is not configured",
)
def test_postgres_review_queue_snapshot_retention_prunes_oldest(tmp_path):
    store = PostgresStorage(
        database_url=POSTGRES_URL,
        artifact_root=str(tmp_path / "artifacts"),
    )
    _assert_retention(store, f"retention-pg-{uuid4()}")
