from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.storage import Storage
from app.worker_service import _record_finding_observation


def _campaign():
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
            ),
        ),
    )


def test_scanner_finding_persists_canonical_asset_endpoint_finding_evidence_chain(tmp_path):
    campaign = _campaign()
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(campaign.model_dump(mode="json"))

    finding = Finding(
        id="strix-fixture",
        title="Fixture issue",
        severity="high",
        asset="https://app.example.test",
        endpoint="/profile",
        summary="fixture",
        evidence=["header mismatch", "response marker"],
        cwe="CWE-284",
        cvss=7.5,
        discovered_by="strix",
        status="validation_required",
    )

    finding_observation_id = _record_finding_observation(store, campaign, finding)
    records = store.list_observations(campaign.id)
    by_id = {item["id"]: item for item in records}

    finding_record = by_id[finding_observation_id]
    endpoint_id = finding_record["parent_ids"][0]
    endpoint_record = by_id[endpoint_id]
    asset_id = endpoint_record["parent_ids"][0]
    asset_record = by_id[asset_id]

    assert asset_record["kind"] == "asset"
    assert endpoint_record["kind"] == "endpoint"
    assert endpoint_record["value"] == "https://app.example.test/profile"
    assert finding_record["kind"] == "finding"
    assert finding_record["metadata"]["cwe"] == "CWE-284"
    assert finding_record["metadata"]["cvss"] == 7.5

    evidence = [
        item for item in records
        if item["kind"] == "evidence" and item["metadata"].get("scanner_evidence")
    ]
    assert len(evidence) == 2
    assert {item["parent_ids"][0] for item in evidence} == {finding_observation_id}
    assert {item["value"] for item in evidence} == {"header mismatch", "response marker"}


def test_scanner_finding_without_endpoint_links_directly_to_asset(tmp_path):
    campaign = _campaign()
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(campaign.model_dump(mode="json"))

    finding = Finding(
        id="nuclei-fixture",
        title="Fixture issue",
        severity="medium",
        asset="https://app.example.test",
        summary="fixture",
        evidence=[],
        discovered_by="nuclei",
        status="validation_required",
    )

    finding_observation_id = _record_finding_observation(store, campaign, finding)
    records = store.list_observations(campaign.id)
    by_id = {item["id"]: item for item in records}

    parent = by_id[by_id[finding_observation_id]["parent_ids"][0]]

    assert parent["kind"] == "asset"
    assert by_id[finding_observation_id]["source"] == "nuclei"
