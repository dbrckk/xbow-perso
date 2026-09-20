from __future__ import annotations

from app.surface_diff import build_surface_diff_intelligence


def test_surface_diff_prioritizes_new_authorized_surface():
    memory = {
        "campaign_id": "c2",
        "previous_campaign_id": "c1",
        "delta": {
            "added": [
                {"kind": "endpoint", "value": "https://app.example.com/api"},
                {"kind": "asset", "value": "new.example.com"},
                {"kind": "technology", "value": "next.js"},
            ],
            "removed": [
                {"kind": "waf", "value": "cloudflare"},
            ],
            "truncated": False,
        },
    }

    result = build_surface_diff_intelligence(memory)

    assert result["baseline_available"] is True
    assert result["execution_influence"] is False
    assert result["scope_expansion"] is False
    assert result["read_only"] is True
    assert result["summary"]["change_count"] == 4
    assert result["summary"]["added_count"] == 3
    assert result["summary"]["removed_count"] == 1
    assert result["summary"]["review_priority"] in {"medium", "high"}
    assert [item["kind"] for item in result["focus"]] == ["asset", "endpoint"]
    assert result["changes"][0]["kind"] == "asset"


def test_surface_diff_is_stable_without_baseline():
    result = build_surface_diff_intelligence(
        {
            "campaign_id": "first",
            "previous_campaign_id": None,
            "delta": {"added": [], "removed": [], "truncated": False},
        }
    )

    assert result["baseline_available"] is False
    assert result["summary"]["change_score"] == 0
    assert result["summary"]["review_priority"] == "stable"
    assert result["focus"] == []


def test_removed_surface_has_lower_weight_than_added_surface():
    result = build_surface_diff_intelligence(
        {
            "campaign_id": "c2",
            "previous_campaign_id": "c1",
            "delta": {
                "added": [{"kind": "endpoint", "value": "https://app.example.com/new"}],
                "removed": [{"kind": "endpoint", "value": "https://app.example.com/old"}],
            },
        }
    )

    added = next(item for item in result["changes"] if item["direction"] == "added")
    removed = next(item for item in result["changes"] if item["direction"] == "removed")
    assert added["weight"] > removed["weight"]
