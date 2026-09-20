from __future__ import annotations

from pathlib import Path

from app.storage import Storage
from app.target_memory import build_target_memory, target_identity


class FakeStore:
    def __init__(self, campaigns, observations):
        self._campaigns = list(campaigns)
        self._observations = dict(observations)

    def list_campaigns(self, *, limit=None):
        items = list(self._campaigns)
        return items if limit is None else items[:limit]

    def list_observations(self, campaign_id):
        return list(self._observations.get(campaign_id, []))


def campaign(
    campaign_id: str,
    *,
    created_at: str,
    updated_at: str,
    authorization: str = "https://hackerone.com/example/policy",
):
    return {
        "id": campaign_id,
        "state": "completed",
        "created_at": created_at,
        "updated_at": updated_at,
        "target": {
            "name": "Example",
            "primary_url": "https://app.example.com/",
            "rules": {
                "authorization_reference": authorization,
                "allowed_targets": ["app.example.com"],
                "denied_targets": [],
            },
        },
    }


def observation(obs_id, kind, value, created_at, source="recon"):
    return {
        "id": obs_id,
        "kind": kind,
        "value": value,
        "source": source,
        "parent_ids": (),
        "metadata": {},
        "created_at": created_at,
    }


def test_target_memory_aggregates_surface_and_builds_delta(monkeypatch):
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_CAMPAIGNS", "10")
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_NODES", "1000")
    old = campaign(
        "old",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T01:00:00+00:00",
    )
    current = campaign(
        "current",
        created_at="2026-09-02T00:00:00+00:00",
        updated_at="2026-09-02T01:00:00+00:00",
    )
    unrelated = campaign(
        "other-program",
        created_at="2026-09-03T00:00:00+00:00",
        updated_at="2026-09-03T01:00:00+00:00",
        authorization="https://other.example/policy",
    )
    store = FakeStore(
        [unrelated, current, old],
        {
            "old": [
                observation("a1", "asset", "APP.EXAMPLE.COM.", "2026-09-01T00:10:00+00:00"),
                observation("e1", "endpoint", "https://app.example.com/login#frag", "2026-09-01T00:11:00+00:00"),
                observation("t1", "technology", " React  19 ", "2026-09-01T00:12:00+00:00"),
            ],
            "current": [
                observation("a2", "asset", "app.example.com", "2026-09-02T00:10:00+00:00"),
                observation("e2", "endpoint", "https://app.example.com/api", "2026-09-02T00:11:00+00:00"),
                observation("w1", "waf", " CloudFlare ", "2026-09-02T00:12:00+00:00"),
            ],
            "other-program": [
                observation("x", "endpoint", "https://app.example.com/private", "2026-09-03T00:10:00+00:00"),
            ],
        },
    )

    memory = build_target_memory(store, current)

    assert memory["read_only"] is True
    assert memory["advisory_only"] is True
    assert memory["campaigns_considered"] == 2
    assert memory["previous_campaign_id"] == "old"
    assert memory["summary"]["nodes"] == 5
    assert memory["summary"]["by_kind"]["asset"] == 1
    assert memory["summary"]["by_kind"]["endpoint"] == 2
    assert memory["summary"]["by_kind"]["technology"] == 1
    assert memory["summary"]["by_kind"]["waf"] == 1
    assert memory["delta"]["added_count"] == 2
    assert memory["delta"]["removed_count"] == 2
    assert memory["delta"]["persistent_count"] == 1
    assert {"kind": "endpoint", "value": "https://app.example.com/api"} in memory["delta"]["added"]
    assert {"kind": "endpoint", "value": "https://app.example.com/login"} in memory["delta"]["removed"]
    assert all(node["value"] != "https://app.example.com/private" for node in memory["nodes"])


def test_target_identity_is_bound_to_authorization_reference():
    one = campaign(
        "one",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T00:00:00+00:00",
    )
    two = campaign(
        "two",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T00:00:00+00:00",
        authorization="https://different.example/policy",
    )
    assert target_identity(one) != target_identity(two)


def test_storage_accepts_form_and_waf_observations(tmp_path: Path):
    store = Storage(
        db_path=str(tmp_path / "xbow.sqlite3"),
        artifact_root=str(tmp_path / "artifacts"),
    )
    doc = campaign(
        "campaign-1",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T00:00:00+00:00",
    )
    store.save_campaign(doc, expected_version=0)

    form = store.put_observation(
        "campaign-1",
        {
            "id": "form:login",
            "kind": "form",
            "value": "POST /login",
            "source": "browser",
            "metadata": {},
        },
    )
    waf = store.put_observation(
        "campaign-1",
        {
            "id": "waf:cloudflare",
            "kind": "waf",
            "value": "Cloudflare",
            "source": "recon",
            "metadata": {},
        },
    )

    assert form["kind"] == "form"
    assert waf["kind"] == "waf"
