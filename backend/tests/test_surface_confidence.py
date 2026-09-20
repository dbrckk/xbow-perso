from __future__ import annotations

from app.surface_confidence import build_surface_confidence


def test_surface_confidence_rewards_multi_source_persistent_nodes():
    memory = {
        "campaign_id": "c4",
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/api",
                "campaign_count": 4,
                "sources": ["crawler", "browser", "endpoint-agent"],
            },
            {
                "kind": "endpoint",
                "value": "https://app.example.com/once",
                "campaign_count": 1,
                "sources": ["crawler"],
            },
        ],
    }
    temporal = {
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/api",
                "classification": "stable",
                "presence_ratio": 1.0,
            },
            {
                "kind": "endpoint",
                "value": "https://app.example.com/once",
                "classification": "new",
                "presence_ratio": 0.25,
            },
        ]
    }

    result = build_surface_confidence(memory, temporal)

    by_value = {item["value"]: item for item in result["nodes"]}
    strong = by_value["https://app.example.com/api"]
    weak = by_value["https://app.example.com/once"]

    assert strong["confidence"] > weak["confidence"]
    assert strong["grade"] == "high"
    assert weak["grade"] == "low"
    assert result["read_only"] is True
    assert result["execution_influence"] is False


def test_surface_confidence_uses_temporal_stability_as_small_component():
    memory = {
        "campaign_id": "c3",
        "nodes": [
            {
                "kind": "technology",
                "value": "react",
                "campaign_count": 2,
                "sources": ["tech-agent"],
            },
            {
                "kind": "technology",
                "value": "vue",
                "campaign_count": 2,
                "sources": ["tech-agent"],
            },
        ],
    }
    temporal = {
        "nodes": [
            {
                "kind": "technology",
                "value": "react",
                "classification": "stable",
                "presence_ratio": 1.0,
            },
            {
                "kind": "technology",
                "value": "vue",
                "classification": "intermittent",
                "presence_ratio": 0.5,
            },
        ]
    }

    result = build_surface_confidence(memory, temporal)
    by_value = {item["value"]: item for item in result["nodes"]}

    assert by_value["react"]["confidence"] > by_value["vue"]["confidence"]


def test_surface_confidence_is_bounded_and_handles_empty_input():
    empty = build_surface_confidence({"campaign_id": "c0", "nodes": []}, {"nodes": []})

    assert empty["summary"]["nodes"] == 0
    assert empty["summary"]["average_confidence"] == 0.0
    assert empty["nodes"] == []

    result = build_surface_confidence(
        {
            "campaign_id": "c1",
            "nodes": [
                {
                    "kind": "asset",
                    "value": "app.example.com",
                    "campaign_count": 999,
                    "sources": ["a", "b", "c", "d", "e"],
                }
            ],
        },
        {
            "nodes": [
                {
                    "kind": "asset",
                    "value": "app.example.com",
                    "classification": "stable",
                    "presence_ratio": 9.0,
                }
            ]
        },
    )

    assert 0.0 <= result["nodes"][0]["confidence"] <= 1.0
