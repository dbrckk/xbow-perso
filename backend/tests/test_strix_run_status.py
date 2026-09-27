import json

import pytest

from app.strix_run_status import StrixRunStatusError, load_strix_run_status


def test_strix_run_status_requires_completed_status(tmp_path):
    run_dir = tmp_path / "strix_runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"status": "completed"}),
        encoding="utf-8",
    )

    result = load_strix_run_status(tmp_path / "strix_runs")

    assert result.completed is True
    assert result.status == "completed"
    assert result.run_json_path.endswith("run.json")


def test_strix_run_status_does_not_treat_stopped_as_completed(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"status": "stopped"}),
        encoding="utf-8",
    )

    result = load_strix_run_status(tmp_path)

    assert result.completed is False
    assert result.status == "stopped"


def test_strix_run_status_fails_closed_without_run_json(tmp_path):
    with pytest.raises(StrixRunStatusError, match="run.json was not produced"):
        load_strix_run_status(tmp_path)


def test_strix_run_status_rejects_oversized_status_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_MAX_STRIX_RUN_JSON_BYTES", "1024")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"status": "completed", "padding": "x" * 2048}),
        encoding="utf-8",
    )

    with pytest.raises(StrixRunStatusError, match="exceeds configured size limit"):
        load_strix_run_status(tmp_path)
