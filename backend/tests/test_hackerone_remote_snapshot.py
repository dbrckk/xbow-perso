from copy import deepcopy

import pytest

from app.hackerone_client import (
    HackerOneClientError,
    fetch_hackerone_program_snapshot,
)
from app.hackerone_scope_import import import_hackerone_structured_scope


class _FakeClient:
    def __init__(self, *, policy="Policy v1", extra_scope=None, exclusion_detail="Do not test status.example.com"):
        self.policy = policy
        self.extra_scope = list(extra_scope or [])
        self.exclusion_detail = exclusion_detail
        self.calls = []

    def get_json(self, path, query=None):
        self.calls.append(("get_json", path))
        if path == "hackers/programs/acme":
            return {
                "data": {
                    "id": "42",
                    "type": "program",
                    "attributes": {
                        "handle": "acme",
                        "name": "Acme Security",
                        "policy": self.policy,
                        "submission_state": "open",
                        "state": "public_mode",
                        "offers_bounties": True,
                        "open_scope": True,
                        "fast_payments": False,
                        "gold_standard_safe_harbor": True,
                    },
                }
            }
        raise AssertionError(path)

    def get_all_pages(self, path):
        self.calls.append(("get_all_pages", path))
        if path == "hackers/programs/acme/structured_scopes":
            return [
                {
                    "id": "scope-1",
                    "type": "structured-scope",
                    "attributes": {
                        "asset_identifier": "app.example.com",
                        "asset_type": "Domain",
                        "eligible_for_bounty": True,
                        "eligible_for_submission": True,
                        "instruction": "Production web app",
                        "max_severity": "critical",
                    },
                },
                *deepcopy(self.extra_scope),
            ]
        if path == "hackers/programs/acme/scope_exclusions":
            return [
                {
                    "id": "exclude-1",
                    "type": "scope-exclusion",
                    "attributes": {
                        "category": "other",
                        "details": self.exclusion_detail,
                    },
                }
            ]
        raise AssertionError(path)


def test_snapshot_collects_complete_scope_and_builds_import_preview():
    client = _FakeClient(
        extra_scope=[
            {
                "id": "scope-2",
                "type": "structured-scope",
                "attributes": {
                    "asset_identifier": "*.api.example.com",
                    "asset_type": "Wildcard",
                    "eligible_for_bounty": True,
                    "eligible_for_submission": True,
                    "instruction": "API hosts",
                    "max_severity": "high",
                },
            }
        ]
    )

    snapshot = fetch_hackerone_program_snapshot("acme", client=client)

    assert snapshot.handle == "acme"
    assert snapshot.program == {
        "handle": "acme",
        "name": "Acme Security",
        "policy": "Policy v1",
        "submission_state": "open",
        "state": "public_mode",
        "offers_bounties": True,
        "open_scope": True,
        "fast_payments": False,
        "gold_standard_safe_harbor": True,
    }
    assert len(snapshot.document["data"]) == 2
    assert snapshot.document["links"] == {}
    imported = import_hackerone_structured_scope(snapshot.document)
    assert imported.complete is True
    assert set(imported.allowed_targets) == {"app.example.com", "*.api.example.com"}
    assert snapshot.preview["complete"] is True
    assert snapshot.preview["allowed_targets"] == ["*.api.example.com", "app.example.com"]
    assert snapshot.preview["assets"][0]["compatible"] is True
    assert len(snapshot.scope_exclusions) == 1
    assert len(snapshot.snapshot_sha256) == 64
    assert client.calls == [
        ("get_json", "hackers/programs/acme"),
        ("get_all_pages", "hackers/programs/acme/structured_scopes"),
        ("get_all_pages", "hackers/programs/acme/scope_exclusions"),
    ]


def test_snapshot_hash_changes_when_program_scope_or_exclusions_change():
    baseline = fetch_hackerone_program_snapshot("acme", client=_FakeClient())
    policy_changed = fetch_hackerone_program_snapshot("acme", client=_FakeClient(policy="Policy v2"))
    scope_changed = fetch_hackerone_program_snapshot(
        "acme",
        client=_FakeClient(
            extra_scope=[
                {
                    "id": "scope-2",
                    "type": "structured-scope",
                    "attributes": {
                        "asset_identifier": "api.example.com",
                        "asset_type": "Domain",
                        "eligible_for_submission": True,
                    },
                }
            ]
        ),
    )
    exclusions_changed = fetch_hackerone_program_snapshot(
        "acme",
        client=_FakeClient(exclusion_detail="Different exclusion"),
    )

    assert baseline.snapshot_sha256 != policy_changed.snapshot_sha256
    assert baseline.snapshot_sha256 != scope_changed.snapshot_sha256
    assert baseline.snapshot_sha256 != exclusions_changed.snapshot_sha256


def test_snapshot_hash_is_stable_when_resource_order_changes():
    scope_a = {
        "id": "scope-a",
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": "a.example.com",
            "asset_type": "Domain",
            "eligible_for_submission": True,
        },
    }
    scope_b = {
        "id": "scope-b",
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": "b.example.com",
            "asset_type": "Domain",
            "eligible_for_submission": True,
        },
    }
    first = fetch_hackerone_program_snapshot("acme", client=_FakeClient(extra_scope=[scope_a, scope_b]))
    second = fetch_hackerone_program_snapshot("acme", client=_FakeClient(extra_scope=[scope_b, scope_a]))

    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.document == second.document


@pytest.mark.parametrize(
    "handle",
    ["", "ACME", "../acme", "acme/program", "acme?debug=1", "-acme", "a" * 129],
)
def test_snapshot_rejects_unsafe_program_handles(handle):
    with pytest.raises(HackerOneClientError, match="handle"):
        fetch_hackerone_program_snapshot(handle, client=_FakeClient())


def test_snapshot_rejects_program_handle_mismatch():
    client = _FakeClient()
    original = client.get_json

    def get_json(path, query=None):
        document = original(path, query)
        document["data"]["attributes"]["handle"] = "other-program"
        return document

    client.get_json = get_json

    with pytest.raises(HackerOneClientError, match="handle mismatch"):
        fetch_hackerone_program_snapshot("acme", client=client)
