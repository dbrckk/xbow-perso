import pytest
from pydantic import ValidationError

from app.main import ProgramRules, TargetInput, is_host_allowed


def test_exact_host_allowed():
    assert is_host_allowed("app.example.com", ["app.example.com"], [])


def test_wildcard_subdomain_allowed():
    assert is_host_allowed("api.example.com", ["*.example.com"], [])


def test_unlisted_host_denied():
    assert not is_host_allowed("evil.example.net", ["*.example.com"], [])


def test_deny_overrides_allow():
    assert not is_host_allowed("admin.example.com", ["*.example.com"], ["admin.example.com"])


def test_target_input_rejects_url_userinfo():
    rules = ProgramRules(
        authorization_reference="AUTH-1",
        allowed_targets=["example.com"],
    )

    with pytest.raises(ValidationError, match="userinfo"):
        TargetInput(
            name="fixture",
            primary_url="https://user:password@example.com/path",
            rules=rules,
        )
