import pytest

from app.agent_registry import agent_by_name, agent_for_action, public_agent_catalog


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


def test_specialized_recon_agents_are_registered_centrally():
    expected = {
        "crawler-agent": "recon:crawl",
        "endpoint-agent": "recon:map_endpoints",
        "tech-agent": "recon:detect_technology",
        "form-agent": "recon:map_forms",
        "browser-agent": "recon:browser_observe",
    }
    for name, action in expected.items():
        profile = agent_by_name(name)
        assert profile.role == "recon"
        assert profile.network_access is True
        assert action in profile.actions


def test_agent_by_name_fails_closed_for_unknown_agent():
    with pytest.raises(ValueError, match="no unique agent registered by name"):
        agent_by_name("unknown-agent")
