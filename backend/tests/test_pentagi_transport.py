from dataclasses import replace
from email.message import Message

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_adapter import build_pentagi_flow_plan
from app.pentagi_execution_guard import issue_pentagi_execution_permit
from app.pentagi_transport import PentagiTransportError, submit_pentagi_flow


class _Response:
    def __init__(self, payload: bytes, *, status: int = 200, content_type: str = "application/json"):
        self._payload = payload
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def getcode(self):
        return self.status

    def read(self, amount: int):
        return self._payload[:amount]


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


def _campaign():
    return Campaign(
        id="transport",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=[],
                max_requests_per_second=1.0,
            ),
        ),
    )


def _enable_admission(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "2.0")


def _plan_and_permit(monkeypatch):
    _enable_admission(monkeypatch)
    campaign = _campaign()
    plan = replace(
        build_pentagi_flow_plan(
            campaign,
            base_url="https://pentagi.example.test",
            model_provider="openai",
        ),
        dry_run=False,
        execution_supported=True,
    )
    return plan, issue_pentagi_execution_permit(campaign, plan)


def test_transport_posts_json_without_redirects(monkeypatch):
    plan, permit = _plan_and_permit(monkeypatch)
    monkeypatch.setenv("XBOW_PENTAGI_TOKEN", "secret-token")
    opener = _Opener(_Response(b'{"data":{"createFlow":{"id":"42"}}}'))
    monkeypatch.setattr("app.pentagi_transport.urllib.request.build_opener", lambda *args: opener)

    result = submit_pentagi_flow(plan, permit)

    assert result.status == 200
    assert result.body["data"]["createFlow"]["id"] == "42"
    assert opener.timeout == 10.0
    assert opener.request.full_url == "https://pentagi.example.test/api/v1/graphql"
    assert opener.request.get_method() == "POST"
    assert opener.request.get_header("Authorization") == "Bearer secret-token"
    assert opener.request.get_header("X-xbow-idempotency-key") == permit.idempotency_key


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://pentagi.example.test/api/v1/graphql",
        "https://user:pass@pentagi.example.test/api/v1/graphql",
        "https://pentagi.example.test/other",
        "https://pentagi.example.test/api/v1/graphql?debug=1",
    ],
)
def test_transport_rejects_unsafe_endpoints(monkeypatch, endpoint):
    plan, permit = _plan_and_permit(monkeypatch)
    monkeypatch.setenv("XBOW_PENTAGI_TOKEN", "secret-token")
    plan = replace(plan, endpoint=endpoint)
    permit = replace(permit, endpoint=endpoint)

    with pytest.raises(PentagiTransportError):
        submit_pentagi_flow(plan, permit)


def test_transport_requires_token_without_leaking_value(monkeypatch):
    plan, permit = _plan_and_permit(monkeypatch)
    monkeypatch.delenv("XBOW_PENTAGI_TOKEN", raising=False)

    with pytest.raises(PentagiTransportError, match="XBOW_PENTAGI_TOKEN is required") as exc:
        submit_pentagi_flow(plan, permit)

    assert "Bearer" not in str(exc.value)


def test_transport_rejects_oversized_response(monkeypatch):
    plan, permit = _plan_and_permit(monkeypatch)
    monkeypatch.setenv("XBOW_PENTAGI_TOKEN", "secret-token")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_RESPONSE_BYTES", "1024")
    opener = _Opener(_Response(b"{" + b"x" * 2048 + b"}"))
    monkeypatch.setattr("app.pentagi_transport.urllib.request.build_opener", lambda *args: opener)

    with pytest.raises(PentagiTransportError, match="size limit"):
        submit_pentagi_flow(plan, permit)


def test_transport_rejects_graphql_errors(monkeypatch):
    plan, permit = _plan_and_permit(monkeypatch)
    monkeypatch.setenv("XBOW_PENTAGI_TOKEN", "secret-token")
    opener = _Opener(_Response(b'{"errors":[{"message":"no"}],"data":null}'))
    monkeypatch.setattr("app.pentagi_transport.urllib.request.build_opener", lambda *args: opener)

    with pytest.raises(PentagiTransportError, match="GraphQL response contains errors"):
        submit_pentagi_flow(plan, permit)


def test_transport_rejects_non_json_content_type(monkeypatch):
    plan, permit = _plan_and_permit(monkeypatch)
    monkeypatch.setenv("XBOW_PENTAGI_TOKEN", "secret-token")
    opener = _Opener(_Response(b"ok", content_type="text/plain"))
    monkeypatch.setattr("app.pentagi_transport.urllib.request.build_opener", lambda *args: opener)

    with pytest.raises(PentagiTransportError, match="not JSON"):
        submit_pentagi_flow(plan, permit)
