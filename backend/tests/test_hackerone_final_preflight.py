from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.hackerone_api as hackerone_api


def _resource(identifier: str = "example.com"):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": "Domain",
            "eligible_for_submission": True,
        },
    }


def _policy():
    return hackerone_api.HackerOneProgramPolicyInput(
        authorization_reference="https://hackerone.com/acme",
        policy_version="snapshot:test",
        reviewed_at="2026-09-21T09:00:00+00:00",
        reviewed_by="reviewer",
        safe_harbor_confirmed=True,
        automated_scanning=True,
        max_requests_per_second=1.0,
        test_account_required=False,
        test_account_constraints="",
        additional_restrictions=[],
        program_notes="reviewed",
    )


def _payload(document):
    return hackerone_api.HackerOneRulesPreviewInput(
        document=document,
        policy=_policy(),
        remote_handle="acme",
        remote_snapshot_sha256="a" * 64,
    )


def _snapshot(document, *, submission_state="open", state="public_mode"):
    return SimpleNamespace(
        handle="acme",
        snapshot_sha256="a" * 64,
        document=document,
        program={
            "handle": "acme",
            "name": "Acme",
            "policy": "policy",
            "submission_state": submission_state,
            "state": state,
        },
        scope_exclusions=(),
        preview={"complete": True, "assets": []},
    )


@pytest.mark.parametrize(
    ("submission_state", "state", "reason"),
    [
        ("paused", "public_mode", "hackerone_submissions_not_open"),
        ("closed", "public_mode", "hackerone_submissions_not_open"),
        ("open", "archived", "hackerone_program_not_open"),
        ("open", "disabled", "hackerone_program_not_open"),
    ],
)
def test_remote_binding_launch_rechecks_current_program_state(
    monkeypatch,
    submission_state,
    state,
    reason,
):
    document = {"data": [_resource()], "links": {}}
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(
            document,
            submission_state=submission_state,
            state=state,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        hackerone_api._verify_remote_binding(
            _payload(document),
            require_open=True,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["reason"] == reason
    assert exc.value.detail["handle"] == "acme"


def test_remote_binding_preview_can_still_inspect_paused_program(monkeypatch):
    document = {"data": [_resource()], "links": {}}
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(document, submission_state="paused"),
    )

    binding = hackerone_api._verify_remote_binding(
        _payload(document),
        require_open=False,
    )

    assert binding["verified"] is True
    assert binding["handle"] == "acme"


def test_live_scan_preflight_fails_closed_with_redacted_reasons(monkeypatch):
    monkeypatch.setattr(
        hackerone_api,
        "build_hackerone_live_readiness",
        lambda dependencies: {
            "live_scan_ready": False,
            "checks": [
                {
                    "id": "scanner_worker",
                    "required": True,
                    "ok": False,
                },
                {
                    "id": "report_sync",
                    "required": False,
                    "ok": False,
                },
            ],
            "scanner_block_reasons": ["scanner_worker_disabled"],
        },
    )

    with pytest.raises(HTTPException) as exc:
        hackerone_api._assert_hackerone_live_scan_ready()

    assert exc.value.status_code == 503
    assert exc.value.detail == {
        "message": "HackerOne live scan preflight is not ready",
        "reason": "hackerone_live_scan_not_ready",
        "failed_checks": ["scanner_worker"],
        "scanner_block_reasons": ["scanner_worker_disabled"],
    }


def test_live_scan_preflight_allows_ready_runtime(monkeypatch):
    monkeypatch.setattr(
        hackerone_api,
        "build_hackerone_live_readiness",
        lambda dependencies: {
            "live_scan_ready": True,
            "checks": [],
            "scanner_block_reasons": [],
        },
    )

    hackerone_api._assert_hackerone_live_scan_ready()
