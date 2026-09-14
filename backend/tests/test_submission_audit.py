from app.submission_audit import (
    audit_campaign_submissions,
    audit_storage_submissions,
)


def test_campaign_submission_audit_aggregates_invalid_reports():
    campaign = {
        "events": [
            {
                "type": "report_submitted",
                "artifact_id": "r1",
                "actor": "operator",
                "platform": "generic",
                "at": "2026-09-14T18:00:00Z",
            },
            {
                "type": "report_approved",
                "artifact_id": "r2",
                "artifact_sha256": "a" * 64,
                "basis_digest": "b" * 64,
                "report_provenance_fingerprint": "c" * 64,
                "reviewer": "reviewer",
                "at": "2026-09-14T18:01:00Z",
            },
        ]
    }

    result = audit_campaign_submissions(campaign, ["r1", "r2"])

    assert result["valid"] is False
    assert result["reports_checked"] == 2
    assert result["invalid_reports"] == 1
    assert result["issue_counts"]["submission_without_active_approval"] == 1
    assert result["invalid_artifact_ids"] == ["r1"]


def test_storage_submission_audit_is_optional_for_simple_backends():
    class Storage:
        def list_campaigns(self):
            return []

    result = audit_storage_submissions(Storage())

    assert result["supported"] is False
    assert result["valid"] is True
    assert result["reports_checked"] == 0


def test_storage_submission_audit_aggregates_campaigns():
    class Storage:
        def list_campaigns(self):
            return [
                {
                    "id": "c1",
                    "events": [
                        {
                            "type": "report_approved",
                            "artifact_id": "r1",
                            "artifact_sha256": "a" * 64,
                            "basis_digest": "b" * 64,
                            "report_provenance_fingerprint": "c" * 64,
                            "reviewer": "reviewer",
                            "at": "2026-09-14T18:00:00Z",
                        }
                    ],
                },
                {
                    "id": "c2",
                    "events": [
                        {
                            "type": "report_submitted",
                            "artifact_id": "r2",
                            "actor": "operator",
                            "platform": "generic",
                            "at": "2026-09-14T18:01:00Z",
                        }
                    ],
                },
            ]

        def list_artifacts(self, campaign_id):
            return [
                {
                    "id": "r1" if campaign_id == "c1" else "r2",
                    "kind": "report",
                }
            ]

    result = audit_storage_submissions(Storage())

    assert result["supported"] is True
    assert result["valid"] is False
    assert result["campaigns_checked"] == 2
    assert result["reports_checked"] == 2
    assert result["invalid_reports"] == 1



def test_submission_audit_detects_stale_approval_provenance():
    campaign = {
        "events": [
            {
                "type": "report_approved",
                "artifact_id": "r1",
                "artifact_sha256": "a" * 64,
                "basis_digest": "b" * 64,
                "report_provenance_fingerprint": "c" * 64,
                "reviewer": "reviewer",
                "at": "2026-09-14T18:00:00Z",
            }
        ]
    }

    result = audit_campaign_submissions(
        campaign,
        ["r1"],
        current_provenance_fingerprint="d" * 64,
    )

    assert result["valid"] is False
    assert result["invalid_reports"] == 1
    assert result["issue_counts"]["approval_provenance_stale"] == 1
