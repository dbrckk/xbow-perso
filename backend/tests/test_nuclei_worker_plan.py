import os

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.worker import WorkerPolicyError, build_nuclei_plan, execute


def _campaign(*, rps: float = 2.0):
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                max_requests_per_second=rps,
            ),
        ),
    )


def _configure_run_root(monkeypatch, tmp_path):
    root = tmp_path / "nuclei-runs"
    monkeypatch.setenv("XBOW_NUCLEI_RUN_ROOT", str(root))
    return root


def test_nuclei_plan_is_dry_run_by_default(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    monkeypatch.delenv("XBOW_ENABLE_ACTIVE_SCANS", raising=False)
    monkeypatch.delenv("XBOW_ENABLE_NUCLEI", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)

    plan = build_nuclei_plan(_campaign(), str(root / "job-1"))

    assert plan.engine == "nuclei"
    assert plan.dry_run is True
    assert plan.command[0] == "nuclei"


def test_nuclei_plan_requires_both_activation_gates(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "false")

    assert build_nuclei_plan(_campaign(), str(root / "job-1")).dry_run is True

    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    plan = build_nuclei_plan(_campaign(), str(root / "job-2"))
    assert plan.dry_run is False


def test_nuclei_plan_is_http_only_bounded_and_non_destructive(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")

    plan = build_nuclei_plan(_campaign(), str(root / "job-1"))
    command = plan.command

    assert command[command.index("-type") + 1] == "http"
    assert command[command.index("-tags") + 1] == "tech,misconfig,exposure"
    assert command[command.index("-exclude-tags") + 1] == "dos,fuzz"
    assert command[command.index("-rate-limit") + 1] == "2"
    assert command[command.index("-concurrency") + 1] == "1"
    assert command[command.index("-bulk-size") + 1] == "1"
    assert command[command.index("-payload-concurrency") + 1] == "1"
    for required in (
        "-disable-unsigned-templates",
        "-no-interactsh",
        "-restrict-local-network-access",
        "-disable-redirects",
        "-no-stdin",
        "-omit-raw",
        "-omit-template",
        "-disable-update-check",
    ):
        assert required in command
    for forbidden in ("-ai", "-dast", "-code", "-headless", "-file", "-template-url"):
        assert forbidden not in command


def test_nuclei_plan_preserves_sub_one_rps_limits(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    plan = build_nuclei_plan(_campaign(rps=0.25), str(root / "job-1"))

    assert plan.command[plan.command.index("-rate-limit") + 1] == "1"
    assert plan.command[plan.command.index("-rate-limit-duration") + 1] == "4s"


def test_nuclei_plan_fails_closed_outside_scope(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    campaign = _campaign()
    campaign.target.rules.allowed_targets = ["other.example.test"]

    with pytest.raises(WorkerPolicyError, match="outside declared scope"):
        build_nuclei_plan(campaign, str(root / "job-1"))


def test_nuclei_execution_uses_isolated_home(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("LLM_API_KEY", "must-not-leak")
    monkeypatch.setenv("HOME", "/tmp/untrusted-home")
    monkeypatch.setenv("XBOW_NUCLEI_ALLOWED_VERSION", "3.99.0")

    captured = {"calls": []}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["calls"].append(command)
        captured["command"] = command
        captured["env"] = kwargs["env"]
        result = Result()
        if command == ["nuclei", "-version"]:
            result.stdout = "Nuclei Engine Version: v3.99.0"
        return result

    monkeypatch.setattr("app.worker.subprocess.run", fake_run)

    plan = build_nuclei_plan(_campaign(), str(root / "job-1"))
    result = execute(plan)

    assert result["status"] == "completed"
    assert captured["env"]["HOME"].endswith(".nuclei-home")
    assert captured["env"]["HOME"] != "/tmp/untrusted-home"
    assert "LLM_API_KEY" not in captured["env"]
    assert os.path.isdir(captured["env"]["HOME"])


def test_nuclei_active_execution_requires_allowlisted_runtime(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.delenv("XBOW_NUCLEI_ALLOWED_VERSION", raising=False)

    plan = build_nuclei_plan(_campaign(), str(root / "job-attest"))

    with pytest.raises(WorkerPolicyError, match="XBOW_NUCLEI_ALLOWED_VERSION is required"):
        execute(plan)


def test_nuclei_active_execution_rejects_version_mismatch(monkeypatch, tmp_path):
    root = _configure_run_root(monkeypatch, tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("XBOW_NUCLEI_ALLOWED_VERSION", "3.99.0")

    class Result:
        returncode = 0
        stdout = "Nuclei Engine Version: v3.98.0"
        stderr = ""

    monkeypatch.setattr("app.worker.subprocess.run", lambda *args, **kwargs: Result())

    plan = build_nuclei_plan(_campaign(), str(root / "job-mismatch"))

    with pytest.raises(WorkerPolicyError, match="version is not allowlisted"):
        execute(plan)
