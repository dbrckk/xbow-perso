import os
from uuid import uuid4

import pytest

from app.postgres_storage import PostgresStorage
from app.storage import CampaignConflictError

POSTGRES_URL = os.getenv("XBOW_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="XBOW_TEST_POSTGRES_URL is not configured")


def _store(tmp_path):
    return PostgresStorage(
        database_url=POSTGRES_URL,
        artifact_root=str(tmp_path / "artifacts"),
    )


def test_postgres_campaign_roundtrip(tmp_path):
    store = _store(tmp_path)
    campaign_id = f"ci-{uuid4()}"
    document = {
        "id": campaign_id,
        "state": "ready",
        "created_at": "x",
        "updated_at": "x",
    }

    assert store.save_campaign(document) == 1
    assert store.get_campaign(campaign_id) == document


def test_postgres_campaign_version_conflict_fails_closed(tmp_path):
    store = _store(tmp_path)
    campaign_id = f"ci-{uuid4()}"
    document = {
        "id": campaign_id,
        "state": "ready",
        "created_at": "x",
        "updated_at": "x",
    }

    assert store.save_campaign(document) == 1
    updated = {**document, "state": "running", "updated_at": "y"}
    assert store.save_campaign(updated, expected_version=1) == 2

    with pytest.raises(CampaignConflictError, match="version conflict"):
        store.save_campaign(
            {**updated, "state": "completed", "updated_at": "z"},
            expected_version=1,
        )
