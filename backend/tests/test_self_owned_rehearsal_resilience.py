from rehearsal_scenarios import (
    run_outbox_recovery_scenario,
    run_worker_failure_scenario,
)


def test_worker_failure_scenario_is_durable_and_bounded(tmp_path, monkeypatch):
    result = run_worker_failure_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "expired_lease_recovered_then_failed_at_attempt_limit"
    assert result.references.counters == {
        "attempts": 2,
        "successful_outcomes": 0,
    }


def test_outbox_crash_window_reconciles_without_duplicate_job(tmp_path, monkeypatch):
    result = run_outbox_recovery_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "audit_reconciled_without_job_recreation"
    assert result.references.counters == {
        "jobs_before": 1,
        "jobs_after": 1,
        "repaired_events": 1,
    }
