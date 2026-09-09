import pytest

from app.main import Campaign, CampaignState, ProgramRules, TargetInput
from app.storage import CampaignConflictError, Storage
from app.worker_service import _campaign, _save


def make_campaign() -> Campaign:
    return Campaign(
        id="c1",
        target=TargetInput(
            name="demo",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        state=CampaignState.ready,
    )


def test_worker_save_rejects_stale_campaign_snapshot(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    first, first_version = _campaign(store, campaign.id)
    stale, stale_version = _campaign(store, campaign.id)
    assert first_version == stale_version == 1

    first.state = CampaignState.running
    assert _save(store, first, first_version) == 2

    stale.state = CampaignState.failed
    with pytest.raises(CampaignConflictError):
        _save(store, stale, stale_version)

    current, version = _campaign(store, campaign.id)
    assert version == 2
    assert current.state == CampaignState.running
