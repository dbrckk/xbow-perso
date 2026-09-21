import base64

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import browser
from app.browser import (
    BrowserExecutionResult,
    BrowserFlowInput,
    BrowserPolicyError,
    BrowserStep,
    _assert_read_only_browser_method,
    _browser_secret,
    _browser_storage_state,
    _flow_dedupe_key,
    _flow_fingerprint,
    execute_browser_flow,
    persist_browser_result,
    queue_browser_flow,
    validate_flow,
)
from app.api_outbox import outbox_snapshot
from app.campaign_audit import append_campaign_event, verify_campaign_event_chain
from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, ProgramRules, TargetInput
from app.storage import CampaignConflictError, Storage


def _campaign() -> Campaign:
    return Campaign(
        target=TargetInput(
            name="Local fixture",
            primary_url="https://app.test.local",
            rules=ProgramRules(
                authorization_reference="fixture-only",
                allowed_targets=["*.test.local"],
                denied_targets=["blocked.test.local"],
            ),
        )
    )


def test_browser_navigation_fails_closed_outside_scope():
    flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://example.com")])
    with pytest.raises(BrowserPolicyError, match="outside declared scope"):
        validate_flow(_campaign(), flow)


def test_browser_denied_target_overrides_wildcard_allow():
    flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://blocked.test.local")])
    with pytest.raises(BrowserPolicyError, match="outside declared scope"):
        validate_flow(_campaign(), flow)


def test_fill_rejects_literal_or_unscoped_secret_reference():
    with pytest.raises(ValidationError):
        BrowserStep(operation="fill", selector="#password")
    with pytest.raises(ValidationError):
        BrowserStep(operation="fill", selector="#password", secret_env="PASSWORD")


def test_browser_is_dry_run_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_BROWSER_AUTOMATION", raising=False)
    flow = BrowserFlowInput(
        steps=[
            BrowserStep(operation="navigate", url="https://app.test.local/login"),
            BrowserStep(operation="screenshot"),
        ]
    )
    result = execute_browser_flow(_campaign(), flow.model_dump(mode="json"))
    assert result.status == "dry_run"
    assert result.observations == [{"steps": 2}]
    assert result.screenshots == []


def test_browser_flow_dedupe_key_is_stable_for_same_campaign_version_and_flow():
    flow = BrowserFlowInput(
        steps=[
            BrowserStep(operation="navigate", url="https://app.test.local/login"),
            BrowserStep(operation="screenshot"),
        ]
    )
    first = _flow_dedupe_key("c1", 4, flow)
    second = _flow_dedupe_key("c1", 4, flow)
    assert first == second
    assert first.startswith("browser:v4:c1:")


def test_browser_flow_dedupe_key_changes_with_version_or_flow():
    first_flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://app.test.local/a")])
    second_flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://app.test.local/b")])
    assert _flow_dedupe_key("c1", 1, first_flow) != _flow_dedupe_key("c1", 2, first_flow)
    assert _flow_dedupe_key("c1", 1, first_flow) != _flow_dedupe_key("c1", 1, second_flow)


def test_browser_artifacts_are_idempotent_per_job(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = _campaign()
    campaign.id = "c1"
    store.save_campaign(campaign.model_dump(mode="json"))
    result = BrowserExecutionResult(
        status="completed",
        observations=[{"step": 1, "operation": "navigate", "url": "https://app.test.local"}],
        screenshots=[("shot.png", b"png-bytes")],
    )

    first = persist_browser_result(store, campaign.id, result, idempotency_prefix="job-1")
    second = persist_browser_result(store, campaign.id, result, idempotency_prefix="job-1")

    assert [item["id"] for item in second] == [item["id"] for item in first]
    assert len(store.list_artifacts(campaign.id)) == 2


def test_invalid_browser_automation_flag_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_BROWSER_AUTOMATION", "sometimes")
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    with pytest.raises(BrowserPolicyError, match="must be a boolean"):
        execute_browser_flow(_campaign(), flow.model_dump(mode="json"))


def test_browser_automation_flag_accepts_explicit_false_values(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_BROWSER_AUTOMATION", "OFF")
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    result = execute_browser_flow(_campaign(), flow.model_dump(mode="json"))

    assert result.status == "dry_run"


def test_browser_automation_respects_program_disable():
    campaign = _campaign()
    campaign.target.rules.automated_scanning = False
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    with pytest.raises(BrowserPolicyError, match="disabled by program rules"):
        validate_flow(campaign, flow)


@pytest.mark.parametrize(
    "flag",
    (
        "destructive_testing",
        "denial_of_service",
        "social_engineering",
        "credential_attacks",
    ),
)
def test_browser_automation_rejects_unsafe_campaign_flags(flag):
    campaign = _campaign()
    setattr(campaign.target.rules, flag, True)
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    with pytest.raises(BrowserPolicyError, match="unsafe campaign flags"):
        validate_flow(campaign, flow)


def test_browser_request_methods_are_read_only():
    for method in ("GET", "HEAD", "OPTIONS", " get "):
        _assert_read_only_browser_method(method)

    for method in ("POST", "PUT", "PATCH", "DELETE", "CONNECT"):
        with pytest.raises(BrowserPolicyError, match="read-only"):
            _assert_read_only_browser_method(method)


def test_browser_surface_observations_are_persistable_shape():
    result = BrowserExecutionResult(
        status="completed",
        observations=[
            {
                "step": 1,
                "operation": "surface_links",
                "urls": ["https://app.test.local/a", "https://app.test.local/b"],
            },
            {
                "step": 1,
                "operation": "surface_forms",
                "forms": [
                    {
                        "action": "https://app.test.local/search",
                        "method": "GET",
                        "input_names": ["q"],
                    }
                ],
            },
            {
                "step": 1,
                "operation": "surface_technologies",
                "technologies": ["next", "generator:fixture"],
            },
        ],
        screenshots=[],
    )

    assert result.observations[0]["operation"] == "surface_links"
    assert result.observations[1]["forms"][0]["method"] == "GET"
    assert "next" in result.observations[2]["technologies"]


def _clear_browser_secret_env(monkeypatch):
    for name in (
        "XBOW_VAULT_ENABLED",
        "XBOW_VAULT_MASTER_KEY",
        "XBOW_VAULT_MASTER_KEY_FILE",
        "XBOW_VAULT_PATH",
        "XBOW_BROWSER_SECRET_TEST_LOGIN",
    ):
        monkeypatch.delenv(name, raising=False)


def _configure_browser_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv(
        "XBOW_VAULT_MASTER_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "vault.json"))


def test_browser_secret_preserves_legacy_env_when_vault_disabled(monkeypatch):
    _clear_browser_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_BROWSER_SECRET_TEST_LOGIN", "legacy-value")

    assert _browser_secret("XBOW_BROWSER_SECRET_TEST_LOGIN") == "legacy-value"


def test_browser_secret_loads_from_vault(monkeypatch, tmp_path):
    from app.secret_vault import set_secret

    _clear_browser_secret_env(monkeypatch)
    _configure_browser_vault(monkeypatch, tmp_path)
    set_secret("browser.test_login", "vault-value")

    assert _browser_secret("XBOW_BROWSER_SECRET_TEST_LOGIN") == "vault-value"


def test_browser_secret_refuses_env_fallback_when_vault_enabled(monkeypatch, tmp_path):
    _clear_browser_secret_env(monkeypatch)
    _configure_browser_vault(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_BROWSER_SECRET_TEST_LOGIN", "must-not-fallback")

    with pytest.raises(BrowserPolicyError, match="legacy XBOW_BROWSER_SECRET_TEST_LOGIN fallback is forbidden"):
        _browser_secret("XBOW_BROWSER_SECRET_TEST_LOGIN")


def test_browser_secret_missing_in_vault_fails_closed(monkeypatch, tmp_path):
    _clear_browser_secret_env(monkeypatch)
    _configure_browser_vault(monkeypatch, tmp_path)

    with pytest.raises(BrowserPolicyError, match="required browser secret is unavailable"):
        _browser_secret("XBOW_BROWSER_SECRET_TEST_LOGIN")


def test_browser_secret_invalid_vault_configuration_fails_closed(monkeypatch):
    _clear_browser_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "sometimes")

    with pytest.raises(BrowserPolicyError, match="browser vault configuration is invalid"):
        _browser_secret("XBOW_BROWSER_SECRET_TEST_LOGIN")



def _browser_flow():
    return BrowserFlowInput(
        steps=[
            BrowserStep(
                operation="navigate",
                url="https://app.test.local/login",
            ),
            BrowserStep(operation="screenshot"),
        ]
    )


def _browser_api_backends(tmp_path, monkeypatch):
    db = str(tmp_path / "browser-api.sqlite3")
    artifacts = str(tmp_path / "browser-artifacts")
    store = Storage(db, artifacts)
    jobs = JobQueue(db)
    campaign = _campaign()
    campaign.id = "browser-api-campaign"
    campaign.state = CampaignState.running
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    monkeypatch.setattr(browser, "create_storage", lambda: store)
    monkeypatch.setattr(browser, "create_queue", lambda: jobs)
    return store, jobs, campaign


def test_browser_queue_uses_backend_factories_and_audited_outbox(
    tmp_path,
    monkeypatch,
):
    store, jobs, campaign = _browser_api_backends(tmp_path, monkeypatch)

    job = queue_browser_flow(campaign.id, _browser_flow())

    assert job["kind"] == "browser_flow"
    assert jobs.stats()["total"] == 1
    persisted = store.get_campaign(campaign.id)
    assert verify_campaign_event_chain(persisted["events"])["valid"] is True

    requested = [
        event
        for event in persisted["events"]
        if event.get("type") == "browser_flow_requested"
    ]
    queued = [
        event
        for event in persisted["events"]
        if event.get("type") == "browser_flow_queued"
    ]
    assert len(requested) == 1
    assert len(queued) == 1
    assert queued[0]["request_id"] == requested[0]["request_id"]
    assert queued[0]["flow_fingerprint"] == requested[0]["flow_fingerprint"]
    assert queued[0]["job_id"] == job["id"]
    assert outbox_snapshot(persisted["events"])["pending_total"] == 0


def test_browser_conflict_before_intent_commit_never_enqueues(
    tmp_path,
    monkeypatch,
):
    store, jobs, campaign = _browser_api_backends(tmp_path, monkeypatch)

    def conflict(document, expected_version=None):
        raise CampaignConflictError("fixture conflict")

    monkeypatch.setattr(store, "save_campaign", conflict)

    with pytest.raises(HTTPException) as exc:
        queue_browser_flow(campaign.id, _browser_flow())

    assert exc.value.status_code == 409
    assert "concurrently" in str(exc.value.detail)
    assert jobs.stats()["total"] == 0


def test_browser_retry_after_enqueue_reuses_existing_job(
    tmp_path,
    monkeypatch,
):
    store, jobs, campaign = _browser_api_backends(tmp_path, monkeypatch)
    flow = _browser_flow()
    fingerprint = _flow_fingerprint(flow)
    request_id = "browser-resume-request"

    document, version = store.get_campaign_record(campaign.id)
    interrupted = Campaign.model_validate(document)
    append_campaign_event(
        interrupted.events,
        {
            "type": "browser_flow_requested",
            "request_id": request_id,
            "flow_fingerprint": fingerprint,
            "at": browser._utcnow(),
        },
    )
    interrupted.updated_at = browser._utcnow()
    store.save_campaign(
        interrupted.model_dump(mode="json"),
        expected_version=version,
    )

    existing = jobs.enqueue(
        campaign.id,
        "browser_flow",
        {
            "campaign_id": campaign.id,
            "steps": flow.model_dump(mode="json")["steps"],
        },
        max_attempts=2,
        dedupe_key=f"browser:{request_id}",
    )

    retried = queue_browser_flow(campaign.id, flow)

    assert retried["id"] == existing["id"]
    assert jobs.stats()["total"] == 1
    persisted = store.get_campaign(campaign.id)
    requested = [
        event
        for event in persisted["events"]
        if event.get("type") == "browser_flow_requested"
        and event.get("request_id") == request_id
    ]
    queued = [
        event
        for event in persisted["events"]
        if event.get("type") == "browser_flow_queued"
        and event.get("request_id") == request_id
    ]
    assert len(requested) == 1
    assert len(queued) == 1
    assert queued[0]["job_id"] == existing["id"]


def test_browser_pending_intent_is_visible_in_outbox(tmp_path, monkeypatch):
    store, _jobs, campaign = _browser_api_backends(tmp_path, monkeypatch)
    flow = _browser_flow()
    fingerprint = _flow_fingerprint(flow)

    document, version = store.get_campaign_record(campaign.id)
    pending = Campaign.model_validate(document)
    append_campaign_event(
        pending.events,
        {
            "type": "browser_flow_requested",
            "request_id": "browser-pending-request",
            "flow_fingerprint": fingerprint,
            "at": browser._utcnow(),
        },
    )
    store.save_campaign(
        pending.model_dump(mode="json"),
        expected_version=version,
    )

    snapshot = outbox_snapshot(store.get_campaign(campaign.id)["events"])

    assert snapshot["pending_total"] == 1
    assert snapshot["pending_by_kind"] == {"browser_flow": 1}
    assert "browser-pending-request" not in str(snapshot)
    assert fingerprint not in str(snapshot)



def test_browser_storage_state_accepts_only_in_scope_session_state(monkeypatch):
    state = {
        "cookies": [
            {
                "name": "session",
                "value": "opaque-secret",
                "domain": ".test.local",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ],
        "origins": [
            {
                "origin": "https://app.test.local",
                "localStorage": [{"name": "theme", "value": "dark"}],
            }
        ],
    }
    monkeypatch.setattr(
        browser,
        "_browser_secret",
        lambda name: __import__("json").dumps(state),
    )

    loaded = _browser_storage_state(
        _campaign(),
        "XBOW_BROWSER_SECRET_TEST_SESSION",
    )

    assert loaded == state
    assert "opaque-secret" not in repr(
        BrowserFlowInput(
            steps=[BrowserStep(operation="navigate", url="https://app.test.local")],
            identity_label="user-a",
            storage_state_secret_env="XBOW_BROWSER_SECRET_TEST_SESSION",
        ).model_dump(mode="json")
    )


def test_browser_storage_state_rejects_out_of_scope_cookie(monkeypatch):
    state = {
        "cookies": [
            {
                "name": "session",
                "value": "secret",
                "domain": "outside.example",
                "path": "/",
            }
        ],
        "origins": [],
    }
    monkeypatch.setattr(
        browser,
        "_browser_secret",
        lambda name: __import__("json").dumps(state),
    )

    with pytest.raises(BrowserPolicyError, match="out-of-scope cookie"):
        _browser_storage_state(
            _campaign(),
            "XBOW_BROWSER_SECRET_TEST_SESSION",
        )


def test_browser_storage_state_rejects_out_of_scope_origin(monkeypatch):
    state = {
        "cookies": [],
        "origins": [{"origin": "https://outside.example", "localStorage": []}],
    }
    monkeypatch.setattr(
        browser,
        "_browser_secret",
        lambda name: __import__("json").dumps(state),
    )

    with pytest.raises(BrowserPolicyError, match="outside declared scope"):
        _browser_storage_state(
            _campaign(),
            "XBOW_BROWSER_SECRET_TEST_SESSION",
        )


def test_browser_dry_run_keeps_identity_label_but_not_session_secret(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_BROWSER_AUTOMATION", raising=False)
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/account")],
        identity_label="role-user",
        storage_state_secret_env="XBOW_BROWSER_SECRET_TEST_SESSION",
    )

    result = execute_browser_flow(_campaign(), flow.model_dump(mode="json"))

    assert result.status == "dry_run"
    assert result.identity_label == "role-user"
    assert result.observations == [{"steps": 1, "identity_label": "role-user"}]
    assert "TEST_SESSION" not in str(result.observations)
