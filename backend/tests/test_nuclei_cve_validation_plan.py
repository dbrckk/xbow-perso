from __future__ import annotations

import pytest

from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.worker import (
    WorkerPolicyError,
    build_nuclei_cve_validation_plan,
    build_nuclei_plan,
)


def _campaign() -> Campaign:
    return Campaign(
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                automated_scanning=True,
                max_requests_per_second=2.0,
            ),
        )
    )


def _finding(**overrides) -> Finding:
    values = {
        "id": "finding-1",
        "title": "Known CVE",
        "severity": "high",
        "asset": "https://app.example.test",
        "endpoint": "https://app.example.test/api",
        "summary": "fixture",
        "status": "validation_required",
        "discovered_by": "nuclei",
        "cve_ids": ["CVE-2026-1207"],
        "template_id": "CVE-2026-1207",
        "template_verified": True,
        "template_max_requests": 1,
    }
    values.update(overrides)
    return Finding(**values)


def _configure(monkeypatch, tmp_path):
    root = tmp_path / "nuclei-runs"
    monkeypatch.setenv("XBOW_NUCLEI_RUN_ROOT", str(root))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "false")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "false")
    return root


def test_discovery_plan_uses_adaptive_cve_selection_by_default(
    monkeypatch,
    tmp_path,
):
    root = _configure(monkeypatch, tmp_path)

    plan = build_nuclei_plan(
        _campaign(),
        str(root / "discovery"),
    )

    tags_index = plan.command.index("-tags")
    assert plan.command[tags_index + 1] == "tech,misconfig,exposure"
    assert "-automatic-scan" in plan.command
    exclude_index = plan.command.index("-exclude-tags")
    excluded = set(plan.command[exclude_index + 1].split(","))
    assert {"dos", "fuzz", "intrusive", "default-login", "bruteforce"} <= excluded


def test_broad_cve_mode_explicitly_adds_cve_and_vuln_tags(
    monkeypatch,
    tmp_path,
):
    root = _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_NUCLEI_CVE_DISCOVERY_MODE", "broad")

    plan = build_nuclei_plan(
        _campaign(),
        str(root / "broad"),
    )

    tags_index = plan.command.index("-tags")
    assert plan.command[tags_index + 1] == (
        "tech,misconfig,exposure,cve,vuln"
    )
    assert "-automatic-scan" not in plan.command


def test_invalid_cve_discovery_mode_fails_closed(monkeypatch, tmp_path):
    root = _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_NUCLEI_CVE_DISCOVERY_MODE", "anything")

    with pytest.raises(WorkerPolicyError, match="must be off, adaptive or broad"):
        build_nuclei_plan(
            _campaign(),
            str(root / "invalid"),
        )


def test_exact_cve_recheck_uses_verified_template_id(monkeypatch, tmp_path):
    root = _configure(monkeypatch, tmp_path)

    plan = build_nuclei_cve_validation_plan(
        _campaign(),
        _finding(),
        str(root / "validation"),
    )

    assert plan.target == "https://app.example.test/api"
    assert "-tags" not in plan.command
    assert "-id" in plan.command
    assert "-automatic-scan" not in plan.command
    id_index = plan.command.index("-id")
    assert plan.command[id_index + 1] == "CVE-2026-1207"
    target_index = plan.command.index("-target")
    assert plan.command[target_index + 1] == "https://app.example.test/api"
    assert "-no-interactsh" in plan.command
    assert "-restrict-local-network-access" in plan.command
    assert "-disable-redirects" in plan.command
    assert plan.dry_run is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"cve_ids": []}, "normalized CVE id"),
        ({"template_id": "../bad"}, "safe template id"),
        ({"template_verified": False}, "verified Nuclei template"),
        ({"template_max_requests": 6}, "request count exceeds"),
        ({"status": "confirmed"}, "validation_required"),
        (
            {"endpoint": "https://evil.invalid/"},
            "outside declared scope",
        ),
        (
            {"endpoint": "https://admin.example.test/"},
            "outside declared scope",
        ),
    ),
)
def test_exact_cve_recheck_fails_closed(monkeypatch, tmp_path, overrides, message):
    root = _configure(monkeypatch, tmp_path)

    with pytest.raises(WorkerPolicyError, match=message):
        build_nuclei_cve_validation_plan(
            _campaign(),
            _finding(**overrides),
            str(root / "validation"),
        )
