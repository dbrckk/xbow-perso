from app.storage import Storage


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
    store.save_campaign(campaign)
    assert store.get_campaign("c1") == campaign

    artifact = store.put_artifact("c1", "http_evidence", b"evidence", media_type="text/plain")
    assert artifact["sha256"] == "ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e"
    listed = store.list_artifacts("c1")
    assert listed[0]["id"] == artifact["id"]
    assert listed[0]["size_bytes"] == 8


def test_artifact_kind_fails_closed(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    try:
        store.put_artifact("c1", "arbitrary", b"x")
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unknown artifact kinds must fail closed")
