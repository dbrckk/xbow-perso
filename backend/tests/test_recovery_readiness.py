from app.main import app
from app.recovery_readiness import build_recovery_readiness


def _preflight(status="ok", legacy=False, config_valid=True):
    return {
        "status": status,
        "job_provenance": {
            "configuration_valid": config_valid,
            "legacy_unprovenanced_jobs_enabled": legacy,
        },
    }


def _queue(safe=True):
    return {"safe_to_resume": safe}


def _audits(valid=True):
    return [
        {
            "campaign": {"valid": valid},
            "worker": {"valid": valid},
            "queue": {"valid": valid},
        }
    ]


def _attestation(valid=True):
    return {"valid": valid}


def test_recovery_readiness_ready_only_when_all_checks_pass():
    result = build_recovery_readiness(
        preflight=_preflight(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        attestation_verification=_attestation(),
    )

    assert result["decision"] == "READY"
    assert result["workers_may_resume"] is True
    assert result["blockers"] == []
    assert result["review_reasons"] == []
    assert result["automatic_worker_start"] is False
    assert result["automatic_mutation"] is False


def test_recovery_readiness_blocks_on_preflight_error():
    result = build_recovery_readiness(
        preflight=_preflight(status="error"),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        attestation_verification=_attestation(),
    )

    assert result["decision"] == "BLOCK"
    assert "deployment_preflight_error" in result["blockers"]
    assert result["workers_may_resume"] is False


def test_recovery_readiness_blocks_on_unsafe_queue():
    result = build_recovery_readiness(
        preflight=_preflight(),
        queue_assessment=_queue(False),
        campaign_audits=_audits(),
        attestation_verification=_attestation(),
    )

    assert result["decision"] == "BLOCK"
    assert "queue_recovery_not_safe" in result["blockers"]


def test_recovery_readiness_blocks_on_invalid_campaign_audit():
    result = build_recovery_readiness(
        preflight=_preflight(),
        queue_assessment=_queue(),
        campaign_audits=_audits(False),
        attestation_verification=_attestation(),
    )

    assert result["decision"] == "BLOCK"
    assert "campaign_audit_invalid" in result["blockers"]


def test_recovery_readiness_blocks_on_invalid_attestation():
    result = build_recovery_readiness(
        preflight=_preflight(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        attestation_verification=_attestation(False),
    )

    assert result["decision"] == "BLOCK"
    assert "signed_recovery_attestation_invalid" in result["blockers"]


def test_recovery_readiness_reviews_when_attestation_missing():
    result = build_recovery_readiness(
        preflight=_preflight(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        attestation_verification=None,
    )

    assert result["decision"] == "REVIEW"
    assert "signed_recovery_attestation_missing" in result["review_reasons"]
    assert result["workers_may_resume"] is False


def test_recovery_readiness_reviews_legacy_provenance_mode():
    result = build_recovery_readiness(
        preflight=_preflight(status="warning", legacy=True),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        attestation_verification=_attestation(),
    )

    assert result["decision"] == "REVIEW"
    assert "legacy_unprovenanced_jobs_enabled" in result["review_reasons"]
    assert result["workers_may_resume"] is False


def test_recovery_readiness_blocks_invalid_provenance_configuration():
    result = build_recovery_readiness(
        preflight=_preflight(status="error", config_valid=False),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        attestation_verification=_attestation(),
    )

    assert result["decision"] == "BLOCK"
    assert "job_provenance_configuration_invalid" in result["blockers"]


def test_recovery_readiness_route_is_exposed():
    assert "/api/recovery/readiness" in app.openapi()["paths"]
