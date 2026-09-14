from app.submission_audit import (
    audit_campaign_submissions,
    audit_storage_submissions,
    audit_submission_events,
    verify_submission_audit,
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
    assert result["issue_class_counts"]["structural"] == 1
    assert result["severity"]["highest"] == "high"
    assert result["severity"]["counts"]["high"] == 1
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
    assert result["issue_class_counts"]["stale"] == 1
    assert result["severity"]["highest"] == "low"
    assert result["severity"]["counts"]["low"] == 1



def test_submission_audit_classifies_missing_approval_metadata():
    campaign = {
        "events": [
            {
                "type": "report_approved",
                "artifact_id": "r1",
                "reviewer": "reviewer",
                "at": "2026-09-14T18:00:00Z",
            }
        ]
    }

    result = audit_campaign_submissions(campaign, ["r1"])

    assert result["valid"] is False
    assert result["issue_class_counts"]["metadata"] == 2
    assert result["severity"]["highest"] == "medium"
    assert result["severity"]["counts"]["medium"] == 2
    assert result["issue_counts"]["approval_missing_basis_digest"] == 1
    assert result["issue_counts"]["approval_missing_artifact_sha256"] == 1



def test_submission_audit_fingerprint_is_deterministic_and_verifiable():
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

    first = audit_submission_events(
        campaign,
        "r1",
        current_provenance_fingerprint="c" * 64,
    )
    second = audit_submission_events(
        campaign,
        "r1",
        current_provenance_fingerprint="c" * 64,
    )

    assert first["schema"] == "submission-audit-v1"
    assert first["fingerprint"] == second["fingerprint"]
    assert len(first["fingerprint"]) == 64
    assert verify_submission_audit(first)["valid"] is True


def test_submission_audit_verifier_detects_tampering():
    campaign = {
        "events": [
            {
                "type": "report_submitted",
                "artifact_id": "r1",
                "actor": "operator",
                "platform": "generic",
                "at": "2026-09-14T18:00:00Z",
            }
        ]
    }

    audit = audit_submission_events(campaign, "r1")
    audit["issues"] = []

    verification = verify_submission_audit(audit)

    assert verification["valid"] is False
    assert verification["fingerprint_valid"] is False
