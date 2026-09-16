from rehearsal_scenarios import (
    run_cancellation_scenario,
    run_policy_drift_scenario,
)


def test_cancellation_scenario_blocks_new_work_and_reports_running_truthfully(
    tmp_path, monkeypatch
):
    result = run_cancellation_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "queued_cancelled_running_reported_new_work_blocked"
    assert result.references.counters == {
        "queued_cancelled": 1,
        "running_jobs": 1,
        "post_cancel_admissions": 0,
    }


def test_policy_drift_blocks_stale_job_before_processor_dispatch(tmp_path, monkeypatch):
    result = run_policy_drift_scenario(tmp_path, monkeypatch)
    assert result.name == "scope_drift_blocks_execution"
    assert result.status == "pass"
    assert result.reason == "policy_fingerprint_mismatch_before_dispatch"
    assert result.references.counters == {"processor_calls": 0}
