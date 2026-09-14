from app.decision_consensus import build_decision_consensus
from app.red_team_decision import RedTeamDecision


def test_scope_integrity_blocks_downstream_work():
    decisions = [
        RedTeamDecision("scope_integrity", 1.0, "scope issue"),
        RedTeamDecision("validate_findings", 0.92, "validate", finding_ids=("f1",)),
    ]

    result = build_decision_consensus(decisions)

    assert result.next_focus == "scope_integrity"
    assert result.blocked is True
    assert result.contradictory is True
    assert result.confidence == 1.0


def test_near_equal_signals_fail_closed():
    decisions = [
        RedTeamDecision("validate_findings", 0.90, "validate", finding_ids=("f1",)),
        RedTeamDecision("strengthen_evidence", 0.87, "evidence", finding_ids=("f1",)),
    ]

    result = build_decision_consensus(decisions)

    assert result.next_focus == "validate_findings"
    assert result.blocked is True
    assert result.contradictory is True
    assert result.confidence == 0.75


def test_clear_leader_remains_advisory_but_unblocked():
    decisions = [
        RedTeamDecision("validate_findings", 0.95, "validate", finding_ids=("f1",)),
        RedTeamDecision("review_surface", 0.70, "surface"),
    ]

    result = build_decision_consensus(decisions)

    assert result.next_focus == "validate_findings"
    assert result.blocked is False
    assert result.contradictory is False
    assert result.confidence == 0.95


def test_empty_decisions_are_stable_idle_consensus():
    result = build_decision_consensus([])

    assert result.next_focus == "idle"
    assert result.blocked is False
    assert result.contradictory is False
    assert result.confidence == 1.0



def test_contradictory_history_is_a_blocking_consensus_signal():
    decisions = [
        RedTeamDecision(
            "review_contradiction",
            0.98,
            "contradictory finding history requires explicit human review",
            finding_ids=("f1",),
        ),
        RedTeamDecision(
            "strengthen_evidence",
            0.84,
            "finding support chains are incomplete",
            finding_ids=("f1",),
        ),
    ]

    result = build_decision_consensus(decisions)

    assert result.next_focus == "review_contradiction"
    assert result.blocked is True
    assert result.contradictory is True
    assert result.confidence == 1.0
    assert "human review" in result.reasons[0]
