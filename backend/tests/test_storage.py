import pytest

from app.storage import ArtifactIntegrityError, CampaignConflictError, Storage


def test_campaign_roundtrip_and_artifact_hash(tmp_path):
    db = tmp_path / "xbow.sqlite3"
    artifacts = tmp_path / "artifacts"
    store = Storage(str(db), str(artifacts))
    campaign = {
        "id": "c1",
        "state": "ready",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "target": {"name": "demo"},
    }
    assert store.save_campaign(campaign) == 1
    assert store.get_campaign("c1") == campaign

    artifact = store.put_artifact("c1", "http_evidence", b"evidence", media_type="text/plain")
    assert artifact["sha256"] == "ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e"
    listed = store.list_artifacts("c1")
    assert listed[0]["id"] == artifact["id"]
    assert listed[0]["size_bytes"] == 8

    metadata, content = store.read_artifact("c1", artifact["id"])
    assert content == b"evidence"
    assert metadata["sha256"] == artifact["sha256"]
    assert "relative_path" not in metadata


def test_campaign_versions_reject_stale_snapshot(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = {"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"}
    assert store.save_campaign(campaign) == 1

    first = store.get_campaign_record("c1")
    second = store.get_campaign_record("c1")
    assert first is not None and second is not None
    first_doc, first_version = first
    second_doc, second_version = second
    assert first_version == second_version == 1

    first_doc["state"] = "running"
    first_doc["updated_at"] = "y"
    assert store.save_campaign(first_doc, expected_version=first_version) == 2

    second_doc["state"] = "failed"
    second_doc["updated_at"] = "z"
    with pytest.raises(CampaignConflictError, match="version conflict"):
        store.save_campaign(second_doc, expected_version=second_version)

    current = store.get_campaign_record("c1")
    assert current is not None
    current_doc, current_version = current
    assert current_version == 2
    assert current_doc["state"] == "running"


def test_campaign_create_rejects_impossible_expected_version(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = {"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"}
    with pytest.raises(CampaignConflictError):
        store.save_campaign(campaign, expected_version=4)
    assert store.get_campaign("c1") is None


def test_artifact_kind_fails_closed(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    with pytest.raises(ValueError, match="unsupported"):
        store.put_artifact("c1", "arbitrary", b"x")


def test_artifact_read_detects_tampering(tmp_path):
    root = tmp_path / "artifacts"
    store = Storage(str(tmp_path / "db.sqlite3"), str(root))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    artifact = store.put_artifact("c1", "validation", b"trusted")
    metadata = store.get_artifact("c1", artifact["id"])
    assert metadata is not None
    (root / metadata["relative_path"]).write_bytes(b"tampered")

    with pytest.raises(ArtifactIntegrityError, match="mismatch"):
        store.read_artifact("c1", artifact["id"])


def test_artifact_lookup_is_campaign_scoped(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    for campaign_id in ("c1", "c2"):
        store.save_campaign({"id": campaign_id, "state": "ready", "created_at": "x", "updated_at": "x"})
    artifact = store.put_artifact("c1", "validation", b"evidence", finding_id="f1")

    assert store.has_artifact("c1", finding_id="f1", kind="validation") is True
    assert store.has_artifact("c2", finding_id="f1", kind="validation") is False
    assert store.get_artifact("c2", artifact["id"]) is None


def test_idempotency_key_returns_existing_artifact(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    first = store.put_artifact("c1", "validation", b"same", idempotency_key="job-1:validation")
    second = store.put_artifact("c1", "validation", b"same", idempotency_key="job-1:validation")

    assert first["id"] == second["id"]
    assert len(store.list_artifacts("c1")) == 1


def test_idempotency_key_rejects_different_content(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    store.put_artifact("c1", "report", b"v1", idempotency_key="job-1:report")

    with pytest.raises(ArtifactIntegrityError, match="idempotency"):
        store.put_artifact("c1", "report", b"v2", idempotency_key="job-1:report")
