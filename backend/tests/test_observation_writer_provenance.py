from app.main import Campaign, ProgramRules, TargetInput
from app.observation_writer import record_artifact
from app.storage import Storage


def test_record_artifact_seals_storage_provenance_against_metadata_override(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    campaign = Campaign(
        id="artifact-provenance-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="authorized-test",
                allowed_targets=["example.test"],
            ),
        ),
    )
    store.save_campaign(campaign.model_dump(mode="json"))

    artifact = store.put_artifact(
        campaign.id,
        "validation",
        b'{"status":"observed"}',
        media_type="application/json",
        idempotency_key="fixture:artifact-provenance",
    )
    observation_id = record_artifact(
        store,
        campaign,
        artifact,
        source="independent-validator",
        metadata={
            "artifact_id": "spoofed-id",
            "artifact_sha256": "0" * 64,
            "artifact_size_bytes": 999999,
            "artifact_media_type": "text/plain",
            "artifact_kind": "validation",
        },
    )

    observation = next(
        item for item in store.list_observations(campaign.id)
        if item["id"] == observation_id
    )

    assert observation["metadata"]["artifact_id"] == artifact["id"]
    assert observation["metadata"]["artifact_sha256"] == artifact["sha256"]
    assert observation["metadata"]["artifact_size_bytes"] == artifact["size_bytes"]
    assert observation["metadata"]["artifact_media_type"] == artifact["media_type"]
    assert observation["metadata"]["artifact_kind"] == "validation"
