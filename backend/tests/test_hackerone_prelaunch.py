from fastapi import HTTPException

from app import hackerone_api


def test_remote_program_launch_gate_blocks_closed_states():
    assert hackerone_api._remote_program_launch_block_reason(
        {"submission_state": "closed", "state": "public_mode"}
    ) == "program_submissions_not_open"
    assert hackerone_api._remote_program_launch_block_reason(
        {"submission_state": "open", "state": "archived"}
    ) == "program_not_currently_open"


def test_remote_program_launch_gate_allows_open_program():
    assert hackerone_api._remote_program_launch_block_reason(
        {"submission_state": "open", "state": "public_mode"}
    ) is None


def test_server_discovery_selection_is_read_only_and_bounded(monkeypatch):
    programs = [
        {
            "handle": "alpha",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 90,
            "opportunity_score": 90,
            "research_focus": ["api_graphql"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "beta",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 80,
            "opportunity_score": 85,
            "research_focus": ["access_control"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "review",
            "status": "REVIEW",
            "offers_bounties": True,
            "value_efficiency_score": 100,
            "opportunity_score": 100,
            "research_focus": ["auth_session"],
            "reasons": [],
            "opportunity_reasons": [],
        },
    ]

    monkeypatch.setattr(
        hackerone_api,
        "hackerone_program_discovery",
        lambda verify_limit=50: {
            "programs": programs,
            "catalog_checked_at": "2026-09-21T10:00:00+00:00",
        },
    )

    result = hackerone_api.hackerone_discovery_selection(limit=2, min_score=50)

    assert result["handles"] == ["alpha", "beta"]
    assert result["read_only"] is True
    assert result["automatic_launch"] is False
    assert result["scope_expansion"] is False
    assert result["requires_launch_revalidation"] is True


def test_reviewed_campaign_input_blocks_program_that_closed_after_review(monkeypatch):
    class Snapshot:
        handle = "alpha"
        snapshot_sha256 = "a" * 64
        program = {
            "name": "Alpha",
            "submission_state": "closed",
            "state": "public_mode",
        }
        document = {"data": []}

    class Store:
        def get_hackerone_review_profile(self, _profile_id):
            raise AssertionError("profile lookup should not happen after close-state gate")

    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda _handle: Snapshot(),
    )

    try:
        hackerone_api._reviewed_campaign_input("alpha", Store())
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["reason"] == "program_submissions_not_open"
    else:
        raise AssertionError("closed program should be blocked")



def test_reviewed_batch_preflight_reports_blocked_members(monkeypatch):
    def fake_reviewed(handle, _store):
        if handle == "closed":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "HackerOne program is no longer launchable",
                    "reason": "program_submissions_not_open",
                    "handles": [handle],
                },
            )

        class Prepared:
            remote_snapshot_sha256 = "b" * 64

        return Prepared()

    monkeypatch.setattr(hackerone_api, "_reviewed_campaign_input", fake_reviewed)
    monkeypatch.setattr("app.main.storage", lambda: object())
    monkeypatch.setattr(hackerone_api, "_raise_if_active_hackerone_batch", lambda _store: None)

    payload = hackerone_api.HackerOneReviewedBatchLaunchInput(
        mode="sequential",
        handles=["alpha", "closed"],
    )
    result = hackerone_api.preflight_reviewed_hackerone_batch(payload)

    assert result["ready"] is False
    assert result["summary"] == {"total": 2, "ready": 1, "blocked": 1}
    blocked = next(item for item in result["members"] if item["handle"] == "closed")
    assert blocked["reason"] == "program_submissions_not_open"
    assert blocked["replaceable"] is True
    assert result["blocked_handles"] == ["closed"]
    assert result["replaceable_handles"] == ["closed"]
    assert result["campaigns_created"] is False
    assert result["automatic_launch"] is False
    assert result["scope_expansion"] is False



def test_go_no_go_requires_runtime_and_batch_ready(monkeypatch):
    monkeypatch.setattr(
        hackerone_api,
        "build_hackerone_live_readiness",
        lambda _deps: {
            "live_scan_ready": False,
            "checks": [{"id": "scanner_worker_live", "required": True, "ok": False}],
        },
    )
    monkeypatch.setattr(
        hackerone_api,
        "preflight_reviewed_hackerone_batch",
        lambda _payload: {
            "ready": False,
            "members": [{
                "handle": "alpha",
                "status": "blocked",
                "reason": "review_profile_required",
            }],
        },
    )
    monkeypatch.setattr("app.main.dependency_readiness", lambda: {"ok": True})

    payload = hackerone_api.HackerOneReviewedBatchLaunchInput(
        mode="sequential",
        handles=["alpha"],
    )
    result = hackerone_api.hackerone_batch_go_no_go(payload)

    assert result["go"] is False
    assert result["runtime_ready"] is False
    assert result["batch_ready"] is False
    assert "scanner_worker_live" in result["blockers"]
    assert "alpha:review_profile_required" in result["blockers"]
    assert result["campaigns_created"] is False
    assert result["automatic_launch"] is False
    assert result["scope_expansion"] is False


def test_go_no_go_returns_go_only_when_runtime_and_batch_are_ready(monkeypatch):
    monkeypatch.setattr(
        hackerone_api,
        "build_hackerone_live_readiness",
        lambda _deps: {"live_scan_ready": True, "checks": []},
    )
    monkeypatch.setattr(
        hackerone_api,
        "preflight_reviewed_hackerone_batch",
        lambda _payload: {
            "ready": True,
            "members": [{"handle": "alpha", "status": "ready"}],
        },
    )
    monkeypatch.setattr("app.main.dependency_readiness", lambda: {"ok": True})

    payload = hackerone_api.HackerOneReviewedBatchLaunchInput(
        mode="parallel",
        handles=["alpha"],
    )
    result = hackerone_api.hackerone_batch_go_no_go(payload)

    assert result["go"] is True
    assert result["blockers"] == []
    assert result["read_only"] is True


def test_reviewed_launch_enforces_go_no_go_before_campaign_creation(monkeypatch):
    monkeypatch.setattr("app.main.storage", lambda: object())
    monkeypatch.setattr(hackerone_api, "_raise_if_active_hackerone_batch", lambda _store: None)
    monkeypatch.setattr(
        hackerone_api,
        "_reviewed_campaign_input",
        lambda _handle, _store: object(),
    )
    monkeypatch.setattr(
        hackerone_api,
        "_runtime_prelaunch_verdict",
        lambda: {
            "runtime_ready": False,
            "runtime": {},
            "blockers": ["scanner_worker_live"],
        },
    )

    payload = hackerone_api.HackerOneReviewedBatchLaunchInput(
        mode="sequential",
        handles=["alpha"],
    )
    try:
        hackerone_api.launch_reviewed_hackerone_batch(payload)
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["reason"] == "batch_go_no_go_blocked"
        assert exc.detail["blockers"] == ["scanner_worker_live"]
    else:
        raise AssertionError("reviewed launch should fail closed on no-go")


def test_reviewed_launch_reuses_handle_preparation_instead_of_full_batch_preflight(monkeypatch):
    calls = []
    prepared = []

    def fake_reviewed(handle, _store):
        calls.append(handle)
        item = hackerone_api.HackerOneCampaignAdmissionInput(
            document={"data": []},
            policy=hackerone_api.HackerOneProgramPolicyInput(
                authorization_reference=f"https://hackerone.com/{handle}",
                policy_version="fixture",
                reviewed_at="2026-09-22T08:00:00+00:00",
                reviewed_by="test",
                safe_harbor_confirmed=True,
                automated_scanning=True,
                max_requests_per_second=1.0,
                test_account_required=False,
                test_account_constraints="",
                additional_restrictions=[],
                program_notes="fixture",
            ),
            target=hackerone_api.HackerOneCampaignTargetInput(
                name=handle,
                primary_url=f"https://{handle}.example.com",
            ),
            remote_handle=handle,
            remote_snapshot_sha256="a" * 64,
        )
        prepared.append(item)
        return item

    monkeypatch.setattr("app.main.storage", lambda: object())
    monkeypatch.setattr(hackerone_api, "_raise_if_active_hackerone_batch", lambda _store: None)
    monkeypatch.setattr(hackerone_api, "_reviewed_campaign_input", fake_reviewed)
    monkeypatch.setattr(
        hackerone_api,
        "_runtime_prelaunch_verdict",
        lambda: {"runtime_ready": True, "runtime": {}, "blockers": []},
    )
    monkeypatch.setattr(
        hackerone_api,
        "hackerone_batch_go_no_go",
        lambda _payload: (_ for _ in ()).throw(
            AssertionError("full batch preflight must not run twice during launch")
        ),
    )
    monkeypatch.setattr(
        hackerone_api,
        "_launch_hackerone_batch_impl",
        lambda payload, verified_remote_bindings=None: {
            "mode": payload.mode,
            "campaign_count": len(payload.campaigns),
            "verified_count": len(verified_remote_bindings or {}),
        },
    )

    payload = hackerone_api.HackerOneReviewedBatchLaunchInput(
        mode="parallel",
        handles=["alpha", "beta"],
    )
    result = hackerone_api.launch_reviewed_hackerone_batch(payload)

    assert calls == ["alpha", "beta"]
    assert len(prepared) == 2
    assert result == {
        "mode": "parallel",
        "campaign_count": 2,
        "verified_count": 2,
    }


def test_reviewed_batch_preflight_does_not_mark_global_upstream_failure_replaceable(monkeypatch):
    def fake_reviewed(_handle, _store):
        raise HTTPException(status_code=503, detail="HackerOne upstream temporarily unavailable")

    monkeypatch.setattr(hackerone_api, "_reviewed_campaign_input", fake_reviewed)
    monkeypatch.setattr("app.main.storage", lambda: object())
    monkeypatch.setattr(hackerone_api, "_raise_if_active_hackerone_batch", lambda _store: None)

    payload = hackerone_api.HackerOneReviewedBatchLaunchInput(
        mode="parallel",
        handles=["alpha"],
    )
    result = hackerone_api.preflight_reviewed_hackerone_batch(payload)

    assert result["ready"] is False
    assert result["blocked_handles"] == ["alpha"]
    assert result["replaceable_handles"] == []
    assert result["members"][0]["replaceable"] is False
    assert result["members"][0]["reason"] == "reviewed_preflight_blocked"


def test_go_no_go_exposes_replaceable_handles(monkeypatch):
    monkeypatch.setattr(
        hackerone_api,
        "_runtime_prelaunch_verdict",
        lambda: {"runtime_ready": True, "runtime": {}, "blockers": []},
    )
    monkeypatch.setattr(
        hackerone_api,
        "preflight_reviewed_hackerone_batch",
        lambda _payload: {
            "ready": False,
            "members": [
                {
                    "handle": "closed",
                    "status": "blocked",
                    "reason": "program_submissions_not_open",
                    "replaceable": True,
                }
            ],
            "replaceable_handles": ["closed"],
        },
    )

    payload = hackerone_api.HackerOneReviewedBatchLaunchInput(
        mode="parallel",
        handles=["closed"],
    )
    result = hackerone_api.hackerone_batch_go_no_go(payload)

    assert result["go"] is False
    assert result["replaceable_handles"] == ["closed"]
    assert "closed:program_submissions_not_open" in result["blockers"]
