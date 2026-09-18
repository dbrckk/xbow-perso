from fastapi.testclient import TestClient

from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.storage import Storage


def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "review.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")
    # Authentication behavior is covered separately; keep these route-semantic
    # tests deterministic even when the CI environment enables mutation TOTP.
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "false")

    campaign = Campaign(
        id="h1-review",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="H1-REVIEW-1",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            Finding(
                id="finding-1",
                title="Fixture exposure",
                severity="medium",
                asset="https://example.test",
                endpoint="https://example.test/profile",
                summary="Initial scanner summary",
                status="validation_required",
                discovered_by="nuclei",
            )
        ],
    )
    Storage(db, artifacts).save_campaign(campaign.model_dump(mode="json"))
    return db, artifacts


def test_human_review_metadata_update_does_not_confirm_finding(tmp_path, monkeypatch):
    db, artifacts = _setup(tmp_path, monkeypatch)
    response = TestClient(app).put(
        "/api/campaigns/h1-review/findings/finding-1/review-metadata",
        json={
            "summary": "Validated exposure summary",
            "impact": "An attacker could disclose profile metadata.",
            "reproduction_steps": [
                "Open the affected profile endpoint.",
                "Observe the exposed metadata.",
            ],
            "remediation": "Restrict the endpoint to authorized users.",
            "cwe": "CWE-200",
            "cvss": 5.3,
            "reviewer": "human-reviewer",
        },
    )

    assert response.status_code == 200
    finding = response.json()
    assert finding["summary"] == "Validated exposure summary"
    assert finding["impact"] == "An attacker could disclose profile metadata."
    assert finding["reproduction_steps"] == [
        "Open the affected profile endpoint.",
        "Observe the exposed metadata.",
    ]
    assert finding["remediation"] == "Restrict the endpoint to authorized users."
    assert finding["cwe"] == "CWE-200"
    assert finding["cvss"] == 5.3
    assert finding["status"] == "validation_required"
    assert finding["validated_by"] is None

    persisted = Storage(db, artifacts).get_campaign("h1-review")
    assert persisted is not None
    event = next(
        item
        for item in persisted["events"]
        if item.get("type") == "finding_review_metadata_updated"
    )
    assert event["finding_id"] == "finding-1"
    assert event["reviewer"] == "human-reviewer"


def test_human_review_metadata_rejects_resolved_rejected_finding(tmp_path, monkeypatch):
    db, artifacts = _setup(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    raw, version = store.get_campaign_record("h1-review")
    raw["findings"][0]["status"] = "rejected"
    raw["findings"][0]["validated_by"] = "human-reviewer"
    store.save_campaign(raw, expected_version=version)

    response = TestClient(app).put(
        "/api/campaigns/h1-review/findings/finding-1/review-metadata",
        json={
            "summary": "Summary",
            "impact": "Impact",
            "reproduction_steps": ["Step"],
            "remediation": "Fix",
            "cwe": "CWE-200",
            "cvss": 1.0,
            "reviewer": "human-reviewer",
        },
    )

    assert response.status_code == 409
    assert "rejected" in str(response.json()["detail"]).lower()
