from __future__ import annotations

from app.surface_temporal import build_temporal_surface_profile


class FakeStore:
    def __init__(self, campaigns, observations):
        self._campaigns = list(campaigns)
        self._observations = dict(observations)

    def list_campaigns(self, *, limit=None):
        items = list(self._campaigns)
        return items if limit is None else items[:limit]

    def list_observations(self, campaign_id):
        return list(self._observations.get(campaign_id, []))


def campaign(campaign_id: str, created_at: str):
    return {
        "id": campaign_id,
        "state": "completed",
        "created_at": created_at,
        "updated_at": created_at,
        "target": {
            "name": "Example",
            "primary_url": "https://app.example.com/",
            "rules": {
                "authorization_reference": "https://hackerone.com/example/policy",
                "allowed_targets": ["app.example.com"],
                "denied_targets": [],
            },
        },
    }


def obs(obs_id: str, kind: str, value: str):
    return {
        "id": obs_id,
        "kind": kind,
        "value": value,
        "source": "recon",
        "parent_ids": (),
        "metadata": {},
        "created_at": "2026-09-01T00:00:00+00:00",
    }


def test_temporal_profile_detects_returning_and_intermittent_surface(monkeypatch):
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_CAMPAIGNS", "20")
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_NODES", "1000")
    c1 = campaign("c1", "2026-09-01T00:00:00+00:00")
    c2 = campaign("c2", "2026-09-02T00:00:00+00:00")
    c3 = campaign("c3", "2026-09-03T00:00:00+00:00")
    c4 = campaign("c4", "2026-09-04T00:00:00+00:00")
    store = FakeStore(
        [c4, c3, c2, c1],
        {
            "c1": [
                obs("a1", "asset", "app.example.com"),
                obs("e1", "endpoint", "https://app.example.com/feature"),
            ],
            "c2": [obs("a2", "asset", "app.example.com")],
            "c3": [
                obs("a3", "asset", "app.example.com"),
                obs("e3", "endpoint", "https://app.example.com/feature"),
            ],
            "c4": [
                obs("a4", "asset", "app.example.com"),
                obs("e4", "endpoint", "https://app.example.com/feature"),
                obs("n4", "endpoint", "https://app.example.com/new"),
            ],
        },
    )

    profile = build_temporal_surface_profile(store, c4)

    assert profile["read_only"] is True
    assert profile["execution_influence"] is False
    assert profile["campaigns_considered"] == 4

    by_value = {item["value"]: item for item in profile["nodes"]}
    returning = by_value["https://app.example.com/feature"]
    newly_seen = by_value["https://app.example.com/new"]
    stable = by_value["app.example.com"]

    assert returning["classification"] in {"returning", "intermittent"}
    assert returning["transitions"] >= 2
    assert newly_seen["classification"] == "new"
    assert stable["classification"] == "stable"


def test_temporal_profile_detects_disappearance(monkeypatch):
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_CAMPAIGNS", "20")
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_NODES", "1000")
    c1 = campaign("c1", "2026-09-01T00:00:00+00:00")
    c2 = campaign("c2", "2026-09-02T00:00:00+00:00")
    store = FakeStore(
        [c2, c1],
        {
            "c1": [
                obs("a1", "asset", "app.example.com"),
                obs("e1", "endpoint", "https://app.example.com/old"),
            ],
            "c2": [obs("a2", "asset", "app.example.com")],
        },
    )

    profile = build_temporal_surface_profile(store, c2)
    by_value = {item["value"]: item for item in profile["nodes"]}

    assert by_value["https://app.example.com/old"]["classification"] == "disappeared"


def test_temporal_profile_ignores_future_campaigns(monkeypatch):
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_CAMPAIGNS", "20")
    monkeypatch.setenv("XBOW_TARGET_MEMORY_MAX_NODES", "1000")
    c1 = campaign("c1", "2026-09-01T00:00:00+00:00")
    c2 = campaign("c2", "2026-09-02T00:00:00+00:00")
    c3 = campaign("c3", "2026-09-03T00:00:00+00:00")
    store = FakeStore(
        [c3, c2, c1],
        {
            "c1": [obs("a1", "asset", "app.example.com")],
            "c2": [obs("a2", "asset", "app.example.com")],
            "c3": [
                obs("a3", "asset", "app.example.com"),
                obs("future", "endpoint", "https://app.example.com/future"),
            ],
        },
    )

    profile = build_temporal_surface_profile(store, c2)

    assert profile["campaign_ids"] == ["c1", "c2"]
    assert all(item["value"] != "https://app.example.com/future" for item in profile["nodes"])
