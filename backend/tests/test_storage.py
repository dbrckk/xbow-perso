import sqlite3
import stat
from contextlib import contextmanager

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


def test_observation_graph_roundtrip_and_parent_integrity(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    asset = store.put_observation(
        "c1",
        {"id": "asset:example.com", "kind": "asset", "value": "example.com", "source": "scope", "metadata": {"in_scope": True}},
    )
    endpoint = store.put_observation(
        "c1",
        {
            "id": "endpoint:/api",
            "kind": "endpoint",
            "value": "/api",
            "source": "browser",
            "parent_ids": (asset["id"],),
        },
    )

    rows = store.list_observations("c1")
    assert [row["id"] for row in rows] == ["asset:example.com", "endpoint:/api"]
    assert rows[1]["parent_ids"] == ("asset:example.com",)
    assert rows[0]["metadata"] == {"in_scope": True}
    assert endpoint["kind"] == "endpoint"


def test_observation_rejects_unknown_parent_and_conflicting_identity(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    with pytest.raises(ValueError, match="unknown parent"):
        store.put_observation(
            "c1",
            {"id": "e1", "kind": "endpoint", "value": "/api", "source": "browser", "parent_ids": ("missing",)},
        )

    first = {"id": "a1", "kind": "asset", "value": "example.com", "source": "scope"}
    assert store.put_observation("c1", first)["id"] == "a1"
    assert store.put_observation("c1", first)["id"] == "a1"
    with pytest.raises(ValueError, match="different content"):
        store.put_observation("c1", {**first, "value": "other.example.com"})


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


def test_artifact_write_rejects_path_traversal_campaign_id(tmp_path):
    root = tmp_path / "artifacts"
    store = Storage(str(tmp_path / "db.sqlite3"), str(root))
    campaign_id = "../escape"
    store.save_campaign({"id": campaign_id, "state": "ready", "created_at": "x", "updated_at": "x"})

    with pytest.raises(ArtifactIntegrityError, match="escaped storage root"):
        store.put_artifact(campaign_id, "validation", b"blocked")

    assert not (tmp_path / "escape").exists()


def test_artifact_write_rejects_symlinked_campaign_directory(tmp_path):
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    outside.mkdir()
    store = Storage(str(tmp_path / "db.sqlite3"), str(root))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    campaign_dir = root / "c1"
    campaign_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ArtifactIntegrityError, match="must not be a symlink"):
        store.put_artifact("c1", "validation", b"blocked")

    assert list(outside.iterdir()) == []


def test_invalid_artifact_size_configuration_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_MAX_ARTIFACT_BYTES", "not-an-integer")
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    with pytest.raises(ValueError, match="must be an integer"):
        store.put_artifact("c1", "validation", b"x")


def test_artifact_size_configuration_rejects_unsafe_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_MAX_ARTIFACT_BYTES", "10")
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    with pytest.raises(ValueError, match="between 1 KiB and 100 MiB"):
        store.put_artifact("c1", "validation", b"x")


def test_artifact_media_type_rejects_header_controls(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    for media_type in ("", "textplain", "text/plain\r\nX-Test: injected"):
        with pytest.raises(ValueError, match="invalid artifact media type"):
            store.put_artifact("c1", "validation", b"x", media_type=media_type)


def test_artifact_file_permissions_are_private(tmp_path):
    root = tmp_path / "artifacts"
    store = Storage(str(tmp_path / "db.sqlite3"), str(root))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    artifact = store.put_artifact("c1", "validation", b"private")
    metadata = store.get_artifact("c1", artifact["id"])
    assert metadata is not None

    mode = stat.S_IMODE((root / metadata["relative_path"]).stat().st_mode)
    assert mode & 0o077 == 0


def test_artifact_file_is_removed_when_metadata_insert_fails(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    store = Storage(str(tmp_path / "db.sqlite3"), str(root))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    original_connect = store.connect
    calls = 0

    @contextmanager
    def flaky_connect():
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise sqlite3.OperationalError("forced metadata failure")
        with original_connect() as db:
            yield db

    monkeypatch.setattr(store, "connect", flaky_connect)

    with pytest.raises(sqlite3.OperationalError, match="forced metadata failure"):
        store.put_artifact("c1", "validation", b"cleanup")

    campaign_dir = root / "c1"
    assert not campaign_dir.exists() or list(campaign_dir.iterdir()) == []


def test_artifact_idempotency_key_rejects_unsafe_values(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    invalid = (
        " ",
        "x" * 201,
        "safe-prefix\nunsafe",
        "safe-prefix\tunsafe",
    )
    for key in invalid:
        with pytest.raises(ValueError, match="idempotency_key"):
            store.put_artifact("c1", "validation", b"x", idempotency_key=key)


def test_storage_rejects_invalid_identifiers(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))

    for campaign_id in ("", "bad\nvalue", "x" * 201):
        with pytest.raises(ValueError, match="campaign_id"):
            store.save_campaign(
                {"id": campaign_id, "state": "ready", "created_at": "x", "updated_at": "x"}
            )

    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    with pytest.raises(ValueError, match="observation_id"):
        store.put_observation(
            "c1",
            {"id": "bad\nobservation", "kind": "asset", "value": "example.test", "source": "test"},
        )

    with pytest.raises(ValueError, match="finding_id"):
        store.put_artifact(
            "c1",
            "validation",
            b"x",
            finding_id="bad\nfinding",
        )

    for artifact_id in ("", "bad\nartifact", "x" * 201):
        with pytest.raises(ValueError, match="artifact_id"):
            store.get_artifact("c1", artifact_id)


def test_has_artifact_validates_filters(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})

    with pytest.raises(ValueError, match="campaign_id"):
        store.has_artifact("bad\ncampaign")

    with pytest.raises(ValueError, match="finding_id"):
        store.has_artifact("c1", finding_id="bad\nfinding")

    with pytest.raises(ValueError, match="unsupported artifact kind"):
        store.has_artifact("c1", kind="arbitrary")
