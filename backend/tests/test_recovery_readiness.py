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



def test_recovery_readiness_history_detects_ready_to_block_regression(tmp_path):
    from app.recovery_readiness import (
        record_recovery_readiness,
        recovery_readiness_history,
    )
    from app.storage import Storage

    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))

    ready = {
        "decision": "READY",
        "blockers": [],
        "review_reasons": [],
        "checks": {"queue_safe_to_resume": True},
        "workers_may_resume": True,
    }
    block = {
        "decision": "BLOCK",
        "blockers": ["queue_recovery_not_safe"],
        "review_reasons": [],
        "checks": {"queue_safe_to_resume": False},
        "workers_may_resume": False,
    }

    record_recovery_readiness(store, ready)
    record_recovery_readiness(store, block)

    history = recovery_readiness_history(store)

    assert history["latest_decision"] == "BLOCK"
    assert history["ready_to_block_regressions"] == 1
    assert history["transitions"][0]["from"] == "READY"
    assert history["transitions"][0]["to"] == "BLOCK"
    assert history["transitions"][0]["ready_to_block"] is True


def test_record_recovery_readiness_is_idempotent_for_same_state(tmp_path):
    from app.recovery_readiness import record_recovery_readiness
    from app.storage import Storage

    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    result = {
        "decision": "REVIEW",
        "blockers": [],
        "review_reasons": ["signed_recovery_attestation_missing"],
        "checks": {"attestation_present": False},
        "workers_may_resume": False,
    }

    first = record_recovery_readiness(store, result)
    second = record_recovery_readiness(store, result)

    snapshots = store.list_recovery_readiness_snapshots()

    assert first["snapshot_fingerprint"] == second["snapshot_fingerprint"]
    assert len(snapshots) == 1


def test_recovery_readiness_history_route_is_exposed():
    assert "/api/recovery/readiness/history" in app.openapi()["paths"]
