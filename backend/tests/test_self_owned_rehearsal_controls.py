from rehearsal_scenarios import run_cancellation_scenario


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
