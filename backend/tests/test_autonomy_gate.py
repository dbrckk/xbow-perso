from app.autonomy_gate import build_autonomy_gate
from app.campaign_risk import CampaignRisk
from app.decision_consensus import DecisionConsensus
from app.main import app


def _risk(*, blocked: bool = False, level: str = "low") -> CampaignRisk:
    return CampaignRisk(
        level=level,
        score=0.1,
        confidence=0.9,
        blocked=blocked,
        factors=(),
        next_focus="review_surface",
    )


def _consensus(*, blocked: bool = False, next_focus: str = "review_surface") -> DecisionConsensus:
    return DecisionConsensus(
        next_focus=next_focus,
        confidence=0.9,
        blocked=blocked,
        contradictory=blocked,
        reasons=("fixture",),
        supporting_kinds=(next_focus,),
    )


def test_gate_allows_only_clean_safe_state():
    gate = build_autonomy_gate(
        automated_scanning=True,
        destructive_testing=False,
        denial_of_service=False,
        social_engineering=False,
        credential_attacks=False,
        runtime_exhausted=False,
        budget_blocked=False,
        failed_jobs=0,
        risk=_risk(),
        consensus=_consensus(),
    )

    assert gate.safe_autonomy_ready is True
    assert gate.human_review_required is False
    assert gate.blockers == ()
    assert "fail_closed_on_conflict" in gate.safeguards


def test_gate_fails_closed_on_policy_runtime_budget_and_health():
    gate = build_autonomy_gate(
        automated_scanning=False,
        destructive_testing=True,
        denial_of_service=True,
        social_engineering=True,
        credential_attacks=True,
        runtime_exhausted=True,
        budget_blocked=True,
        failed_jobs=2,
        risk=_risk(blocked=True, level="critical"),
        consensus=_consensus(blocked=True),
    )

    assert gate.safe_autonomy_ready is False
    assert gate.human_review_required is True
    assert set(gate.blockers) == {
        "automated_scanning_disabled",
        "budget_blocked",
        "campaign_risk_blocked",
        "credential_attacks_enabled",
        "decision_consensus_blocked",
        "denial_of_service_enabled",
        "destructive_testing_enabled",
        "failed_jobs",
        "runtime_exhausted",
        "social_engineering_enabled",
    }


def test_report_focus_always_requires_human_review():
    gate = build_autonomy_gate(
        automated_scanning=True,
        destructive_testing=False,
        denial_of_service=False,
        social_engineering=False,
        credential_attacks=False,
        runtime_exhausted=False,
        budget_blocked=False,
        failed_jobs=0,
        risk=_risk(),
        consensus=_consensus(next_focus="review_for_report"),
    )

    assert gate.safe_autonomy_ready is False
    assert gate.human_review_required is True
    assert gate.next_focus == "review_for_report"


def test_autonomy_gate_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/autonomy-gate" in app.openapi()["paths"]
