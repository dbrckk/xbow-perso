from app.high_value_intelligence import build_high_value_intelligence, public_case_lessons
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _focuses(graph):
    return {
        item["family"]: item
        for item in build_high_value_intelligence(graph)["focuses"]
    }


def test_public_case_lessons_are_bounded_and_evidence_oriented():
    cases = public_case_lessons()

    assert 4 <= len(cases) <= 20
    assert any(case.documented_reward_usd == 25000 for case in cases)
    assert any(case.documented_reward_usd == 20000 for case in cases)
    assert all(case.source_url.startswith("https://www.hackerone.com/") for case in cases)
    assert all(case.observation_goals for case in cases)


def test_graphql_surface_prioritizes_graphql_authorization_lessons():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "tech:graphql",
            "technology",
            "GraphQL",
            "recon:httpx",
        )
    )
    graph.add(
        Observation(
            "endpoint:graphql",
            "endpoint",
            "https://example.test/graphql",
            "recon:katana",
        )
    )

    focuses = _focuses(graph)

    assert focuses["graphql-authorization"]["score"] > 35
    assert focuses["graphql-data-segregation"]["score"] > 35
    assert "graphql" in " ".join(focuses["graphql-authorization"]["reasons"]).lower()


def test_auth_and_server_side_fetch_signals_raise_matching_families():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "endpoint:mfa",
            "endpoint",
            "https://example.test/account/mfa/reset",
            "recon:crawl",
        )
    )
    graph.add(
        Observation(
            "form:webhook",
            "form",
            "https://example.test/integrations/webhook",
            "recon:crawl",
            metadata={"method": "GET", "input_names": ["callback_url"]},
        )
    )

    focuses = _focuses(graph)

    assert focuses["authentication-state-machine"]["score"] > 35
    assert focuses["server-side-fetch-boundaries"]["score"] > 35


def test_high_value_intelligence_is_advisory_only():
    result = build_high_value_intelligence(ObservationGraph())

    assert result["advisory_only"] is True
    assert result["scope_expansion"] is False
    assert result["automatic_exploitation"] is False



def test_transaction_reconciliation_signals_raise_business_invariant_focus():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "endpoint:withdraw",
            "endpoint",
            "https://example.test/api/withdrawals/transaction/status",
            "recon:katana",
        )
    )

    focuses = _focuses(graph)

    assert focuses["transaction-reconciliation-invariants"]["score"] > 35
    goals = " ".join(
        focuses["transaction-reconciliation-invariants"]["observation_goals"]
    ).lower()
    assert "reconciliation" in goals
    assert "idempotency" in goals



def test_high_value_intelligence_route_is_exposed():
    assert (
        "/api/campaigns/{campaign_id}/high-value-intelligence"
        in app.openapi()["paths"]
    )
