from types import SimpleNamespace

from app.hackerone_review_draft import build_hackerone_review_draft


def _snapshot():
    return SimpleNamespace(
        handle="alpha",
        snapshot_sha256="a" * 64,
        program={
            "name": "Alpha Security",
            "offers_bounties": True,
            "gold_standard_safe_harbor": True,
            "submission_state": "open",
            "state": "public_mode",
            "policy": "Policy text",
        },
        document={"data": []},
        preview={
            "complete": True,
            "assets": [
                {
                    "identifier": "*.wild.example.com",
                    "asset_type": "Wildcard",
                    "eligible_for_submission": True,
                    "compatible": True,
                },
                {
                    "identifier": "app.example.com",
                    "asset_type": "Domain",
                    "eligible_for_submission": True,
                    "compatible": True,
                },
            ],
        },
    )


def test_review_draft_prefills_only_deterministic_fields():
    draft = build_hackerone_review_draft(_snapshot())

    assert draft["prefill"]["name"] == "Alpha Security"
    assert draft["prefill"]["primary_url"] == "https://app.example.com"
    assert draft["prefill"]["authorization_reference"] == "https://hackerone.com/alpha"
    assert draft["prefill"]["policy_version"] == "snapshot:" + ("a" * 16)
    assert "safe_harbor_confirmed" in draft["manual_required"]
    assert "automated_scanning" in draft["manual_required"]
    assert draft["automatic_confirmation"] is False
    assert draft["automatic_launch"] is False
    assert draft["scope_expansion"] is False


def test_review_draft_does_not_invent_primary_url_without_plain_domain():
    snapshot = _snapshot()
    snapshot.preview["assets"] = [
        {
            "identifier": "*.example.com",
            "asset_type": "Wildcard",
            "eligible_for_submission": True,
            "compatible": True,
        }
    ]

    draft = build_hackerone_review_draft(snapshot)

    assert draft["prefill"]["primary_url"] is None
