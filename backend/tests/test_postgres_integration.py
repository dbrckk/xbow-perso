import os
from uuid import uuid4

import pytest

from app.postgres_storage import PostgresStorage

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


def test_postgres_health_is_minimal_and_healthy(tmp_path):
    store = _store(tmp_path)

    health = store.health()

    assert health["ok"] is True
    assert health["storage"] == "postgresql"
    assert "password" not in str(health).lower()
