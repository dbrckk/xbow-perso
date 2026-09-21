from app.runtime_gap_analysis import rank_runtime_capability_gaps, runtime_capability_snapshot


def test_runtime_snapshot_is_redacted_and_readiness_only():
    snapshot = runtime_capability_snapshot(
        scanner={"dispatch_ready": False, "mode": "disabled"},
        recon={"dispatch_ready": True, "mode": "builtin_only"},
        browser_available=True,
    )
    assert snapshot == {
        "scanner": False,
        "recon": True,
        "browser": True,
        "scanner_mode": "disabled",
        "recon_mode": "builtin_only",
        "contains_secrets": False,
    }


def test_missing_high_evidence_gap_ranks_above_partial_gap():
    gaps = [
        {
            "category": "business_logic",
            "status": "missing",
            "evidence_score": 20,
            "high_critical_count": 4,
        },
        {
            "category": "api_graphql",
            "status": "partial",
            "evidence_score": 20,
            "high_critical_count": 4,
        },
    ]
    ranked = rank_runtime_capability_gaps(
        gaps,
        {"browser": True, "recon": True, "scanner": False},
    )
    assert ranked[0]["category"] == "business_logic"
    assert ranked[0]["investment_priority"] > ranked[1]["investment_priority"]


def test_runtime_readiness_never_enables_tools_or_scope():
    ranked = rank_runtime_capability_gaps(
        [{
            "category": "injection_rce",
            "status": "partial",
            "evidence_score": 30,
            "high_critical_count": 5,
        }],
        {"browser": True, "recon": True, "scanner": True},
    )
    item = ranked[0]
    assert item["runtime_coverage"] == "ready"
    assert item["automatic_tool_enablement"] is False
    assert item["scope_expansion"] is False
    assert item["advisory_only"] is True
