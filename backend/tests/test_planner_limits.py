from types import SimpleNamespace

from app.observation_graph import AdaptivePlanner, Observation, ObservationGraph
from app.planner_limits import PlannerLimitConfigError, planner_limits

import pytest


def _campaign():
    return SimpleNamespace(
        target=SimpleNamespace(
            primary_url="https://example.com",
            rules=SimpleNamespace(automated_scanning=True),
        ),
        findings=[],
    )


def test_planner_limits_use_safe_defaults(monkeypatch):
    for name in (
        "XBOW_PLANNER_MAX_OBSERVATIONS",
        "XBOW_PLANNER_MAX_ENDPOINTS",
        "XBOW_PLANNER_MAX_FINDINGS",
    ):
        monkeypatch.delenv(name, raising=False)

    limits = planner_limits()

    assert limits.max_observations == 5000
    assert limits.max_endpoints == 1500
    assert limits.max_findings == 250


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("XBOW_PLANNER_MAX_OBSERVATIONS", "99"),
        ("XBOW_PLANNER_MAX_ENDPOINTS", "0"),
        ("XBOW_PLANNER_MAX_FINDINGS", "not-an-int"),
    ],
)
def test_planner_limits_reject_invalid_configuration(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(PlannerLimitConfigError):
        planner_limits()


def test_planner_stops_when_endpoint_bound_is_exceeded(monkeypatch):
    monkeypatch.setenv("XBOW_PLANNER_MAX_ENDPOINTS", "10")
    graph = ObservationGraph()
    graph.add(Observation("asset:1", "asset", "example.com", "test"))
    for index in range(11):
        graph.add(
            Observation(
                f"endpoint:{index}",
                "endpoint",
                f"https://example.com/{index}",
                "test",
                parent_ids=("asset:1",),
            )
        )

    action = AdaptivePlanner().plan(_campaign(), graph)[0]

    assert action.kind == "stop"
    assert "endpoint limit exceeded" in action.reason
    assert "11 > 10" in action.reason


def test_planner_stops_when_finding_bound_is_exceeded(monkeypatch):
    monkeypatch.setenv("XBOW_PLANNER_MAX_FINDINGS", "1")
    graph = ObservationGraph()
    graph.add(Observation("asset:1", "asset", "example.com", "test"))
    graph.add(
        Observation(
            "endpoint:1",
            "endpoint",
            "https://example.com/",
            "test",
            parent_ids=("asset:1",),
        )
    )
    for index in range(2):
        graph.add(
            Observation(
                f"finding:{index}",
                "finding",
                f"candidate-{index}",
                "test",
                parent_ids=("endpoint:1",),
            )
        )

    action = AdaptivePlanner().plan(_campaign(), graph)[0]

    assert action.kind == "stop"
    assert "finding limit exceeded" in action.reason


def test_planner_fails_closed_on_invalid_limit_configuration(monkeypatch):
    monkeypatch.setenv("XBOW_PLANNER_MAX_ENDPOINTS", "invalid")

    action = AdaptivePlanner().plan(_campaign(), ObservationGraph())[0]

    assert action.kind == "stop"
    assert action.reason == "invalid planner safety limit configuration"
