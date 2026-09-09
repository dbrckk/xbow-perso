from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.report_approval import (
    approval_event,
    approval_event_from_storage,
    approval_status,
    approval_status_from_storage,
    revocation_event,
)
from app.storage import ArtifactIntegrityError, Storage


def _campaign() -> Campaign:
    campaign = Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    campaign.findings.append(
        Finding(
            id="f1",
            title="confirmed fixture",
            severity="medium",
            asset="https://example.test",
            summary="bounded fixture",
            impact="fixture impact",
            remediation="fixture remediation",
            status="confirmed",
            discovered_by="scanner",
            validated_by="independent-validator",
        )
    )
    return campaign


def _artifact() -> dict:
    return {
        "id": "report-1",
        "kind": "report",
        "sha256": "a" * 64,
    }


def _store(tmp_path, campaign: Campaign) -> Storage:
    store = Storage(str(tmp_path / "xbow.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    return store


def test_exact_report_and_campaign_state_can_be_approved():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))

    status = approval_status(campaign, artifact)

    assert status.approved is True
    assert status.stale is False
    assert status.reviewer == "human-reviewer"


def test_campaign_change_invalidates_existing_approval():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))
    campaign.findings[0].impact = "changed after approval"

    status = approval_status(campaign, artifact)

    assert status.approved is False
    assert status.stale is True


def test_report_hash_change_invalidates_existing_approval():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))
    artifact = {**artifact, "sha256": "b" * 64}

    status = approval_status(campaign, artifact)

    assert status.approved is False
    assert status.stale is True


def test_revocation_disables_approval():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))
    campaign.events.append(revocation_event(artifact["id"], "human-reviewer", "2026-09-09T21:05:00Z"))

    status = approval_status(campaign, artifact)

    assert status.approved is False
    assert status.stale is False


def test_non_report_artifact_cannot_be_approved():
    campaign = _campaign()
    artifact = {**_artifact(), "kind": "http_evidence"}

    try:
        approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z")
    except ValueError as exc:
        assert "only report artifacts" in str(exc)
    else:
        raise AssertionError("approval must reject non-report artifacts")


def test_storage_backed_approval_verifies_report_bytes(tmp_path):
    campaign = _campaign()
    store = _store(tmp_path, campaign)
    artifact = store.put_artifact(
        campaign.id,
        "report",
        b"verified report draft",
        media_type="text/markdown",
    )

    event = approval_event_from_storage(
        campaign,
        store,
        artifact["id"],
        "human-reviewer",
        "2026-09-09T21:00:00Z",
    )
    campaign.events.append(event)

    status = approval_status_from_storage(campaign, store, artifact["id"])

    assert status.approved is True
    assert status.artifact_sha256 == artifact["sha256"]


def test_tampered_report_bytes_cannot_be_approved_or_reported_as_approved(tmp_path):
    campaign = _campaign()
    store = _store(tmp_path, campaign)
    artifact = store.put_artifact(
        campaign.id,
        "report",
        b"verified report draft",
        media_type="text/markdown",
    )
    campaign.events.append(
        approval_event_from_storage(
            campaign,
            store,
            artifact["id"],
            "human-reviewer",
            "2026-09-09T21:00:00Z",
        )
    )

    metadata = store.get_artifact(campaign.id, artifact["id"])
    assert metadata is not None
    (store.artifact_root / metadata["relative_path"]).write_bytes(b"tampered report draft")

    for check in (
        lambda: approval_event_from_storage(
            campaign,
            store,
            artifact["id"],
            "human-reviewer",
            "2026-09-09T21:05:00Z",
        ),
        lambda: approval_status_from_storage(campaign, store, artifact["id"]),
    ):
        try:
            check()
        except ArtifactIntegrityError:
            pass
        else:
            raise AssertionError("tampered report bytes must fail integrity verification")
