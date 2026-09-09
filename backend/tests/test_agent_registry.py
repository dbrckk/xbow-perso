import pytest

from app.agent_registry import agent_for_action, public_agent_catalog


def test_agent_registry_routes_every_planner_action():
    expected = {
        "inventory": "control",
        "crawl": "recon",
        "scan": "analysis",
        "validate": "validation",
        "report": "reporting",
        "stop": "control",
    }
    for action, role in expected.items():
        assert agent_for_action(action).role == role


def test_agent_registry_fails_closed_for_unknown_action():
    with pytest.raises(ValueError, match="no unique agent"):
        agent_for_action("unknown")


def test_public_catalog_contains_no_destructive_capability():
    serialized = str(public_agent_catalog()).lower()
    assert "rce builder" not in serialized
    assert "auth bypass" not in serialized
    assert "exploit executor" not in serialized
