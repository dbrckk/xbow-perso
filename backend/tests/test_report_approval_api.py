from fastapi.testclient import TestClient

from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.storage import Storage


TOKEN = "report-approval-test-" + "a" * 32


def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "approval.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_API_TOKEN_FILE", raising=False)
    monkeypatch.setenv("XBOW_API_TOKEN", TOKEN)
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "false")

    campaign = Campaign(
        id="h1-report-approval",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="H1-APPROVAL-1",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            Finding(
                id="finding-1",
                title="Confirmed fixture",
                severity="medium",
                asset="https://example.test",
                endpoint="https://example.test/profile",
                summary="Validated issue.",
                impact="Fixture impact.",
                remediation="Fixture remediation.",
                reproduction_steps=["Open the endpoint."],
                cwe="CWE-200",
                cvss=5.3,
                status="confirmed",
                discovered_by="nuclei",
                validated_by="human-reviewer",
            )
        ],
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    artifact = store.put_artifact(
        campaign.id,
        "report",
        b"# HackerOne report\n",
        media_type="text/markdown",
        idempotency_key="fixture:report:hackerone",
    )
    return store, artifact


def _headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_report_approval_api_binds_exact_artifact_and_campaign_state(tmp_path, monkeypatch):
    store, artifact = _setup(tmp_path, monkeypatch)
    client = TestClient(app)

    initial = client.get(
        f"/api/campaigns/h1-report-approval/reports/{artifact['id']}/approval",
        headers=_headers(),
    )
    assert initial.status_code == 200
    assert initial.json()["approved"] is False
    assert initial.json()["stale"] is False

    approved = client.post(
        f"/api/campaigns/h1-report-approval/reports/{artifact['id']}/approval",
        headers=_headers(),
        json={"reviewer": "human-reviewer"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["approved"] is True
    assert body["stale"] is False
    assert body["reviewer"] == "human-reviewer"
    assert body["artifact_sha256"] == artifact["sha256"]

    persisted = store.get_campaign("h1-report-approval")
    event = next(item for item in persisted["events"] if item.get("type") == "report_approved")
    assert event["artifact_id"] == artifact["id"]
    assert event["artifact_sha256"] == artifact["sha256"]


def test_report_approval_becomes_stale_when_submission_state_changes(tmp_path, monkeypatch):
    store, artifact = _setup(tmp_path, monkeypatch)
    client = TestClient(app)
    endpoint = f"/api/campaigns/h1-report-approval/reports/{artifact['id']}/approval"

    assert client.post(
        endpoint,
        headers=_headers(),
        json={"reviewer": "human-reviewer"},
    ).status_code == 200

    raw, version = store.get_campaign_record("h1-report-approval")
    raw["findings"][0]["impact"] = "Changed after approval."
    store.save_campaign(raw, expected_version=version)

    status = client.get(endpoint, headers=_headers())
    assert status.status_code == 200
    assert status.json()["approved"] is False
    assert status.json()["stale"] is True


def test_report_approval_can_be_revoked_explicitly(tmp_path, monkeypatch):
    store, artifact = _setup(tmp_path, monkeypatch)
    client = TestClient(app)
    endpoint = f"/api/campaigns/h1-report-approval/reports/{artifact['id']}/approval"

    assert client.post(
        endpoint,
        headers=_headers(),
        json={"reviewer": "human-reviewer"},
    ).status_code == 200

    revoked = client.post(
        endpoint + "/revoke",
        headers=_headers(),
        json={"reviewer": "human-reviewer"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["approved"] is False
    assert revoked.json()["stale"] is False

    persisted = store.get_campaign("h1-report-approval")
    assert persisted["events"][-1]["type"] == "report_approval_revoked"


def test_report_approval_rejects_tampered_report_bytes(tmp_path, monkeypatch):
    store, artifact = _setup(tmp_path, monkeypatch)
    metadata = store.get_artifact("h1-report-approval", artifact["id"])
    (store.artifact_root / metadata["relative_path"]).write_bytes(b"tampered")

    response = TestClient(app).post(
        f"/api/campaigns/h1-report-approval/reports/{artifact['id']}/approval",
        headers=_headers(),
        json={"reviewer": "human-reviewer"},
    )
    assert response.status_code == 409
    assert "integrity" in str(response.json()["detail"]).lower()


def test_report_approval_route_rejects_non_report_artifact(tmp_path, monkeypatch):
    store, _artifact = _setup(tmp_path, monkeypatch)
    evidence = store.put_artifact(
        "h1-report-approval",
        "http_evidence",
        b"fixture",
        media_type="application/json",
    )

    response = TestClient(app).get(
        f"/api/campaigns/h1-report-approval/reports/{evidence['id']}/approval",
        headers=_headers(),
    )
    assert response.status_code == 400
    assert "report" in str(response.json()["detail"]).lower()
