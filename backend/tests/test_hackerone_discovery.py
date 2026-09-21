from app.hackerone_discovery import build_program_discovery


def _program(handle="alpha", **overrides):
    value = {
        "handle": handle,
        "name": handle.title(),
        "submission_state": "open",
        "state": "public_mode",
        "offers_bounties": True,
        "gold_standard_safe_harbor": True,
    }
    value.update(overrides)
    return value


def test_exact_profile_and_snapshot_is_ready():
    result = build_program_discovery(
        programs=[_program()],
        review_profiles=[{"handle": "alpha", "snapshot_sha256": "abc"}],
        intelligence={"program_signals": {"alpha": {"historical_value_score": 12}}},
        verified_snapshots={"alpha": "abc"},
        runtime={"recon": True, "scanner": False},
        catalog_changes={},
    )
    item = result["programs"][0]
    assert item["status"] == "READY"
    assert item["exact_review_profile"] is True
    assert item["automatic_launch"] is False


def test_saved_profile_with_changed_snapshot_requires_review():
    result = build_program_discovery(
        programs=[_program()],
        review_profiles=[{"handle": "alpha", "snapshot_sha256": "old"}],
        intelligence={},
        verified_snapshots={"alpha": "new"},
        runtime={},
        catalog_changes={},
    )
    item = result["programs"][0]
    assert item["status"] == "REVIEW"
    assert "saved_profile_requires_snapshot_revalidation" in item["reasons"]


def test_closed_program_is_blocked_even_with_matching_profile():
    result = build_program_discovery(
        programs=[_program(submission_state="closed")],
        review_profiles=[{"handle": "alpha", "snapshot_sha256": "abc"}],
        intelligence={},
        verified_snapshots={"alpha": "abc"},
        runtime={},
        catalog_changes={},
    )
    assert result["programs"][0]["status"] == "BLOCKED"


def test_ready_items_sort_before_review_and_blocked():
    result = build_program_discovery(
        programs=[
            _program("review"),
            _program("blocked", submission_state="closed"),
            _program("ready"),
        ],
        review_profiles=[{"handle": "ready", "snapshot_sha256": "same"}],
        intelligence={},
        verified_snapshots={"ready": "same"},
        runtime={},
        catalog_changes={},
    )
    assert [item["status"] for item in result["programs"]] == [
        "READY", "REVIEW", "BLOCKED"
    ]
    assert result["scope_expansion"] is False
