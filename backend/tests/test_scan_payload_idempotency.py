from app.main import Campaign, ProgramRules, TargetInput, policy_receipt, sanitized_scan_payload


def _campaign() -> Campaign:
    return Campaign(
        id="c1",
        target=TargetInput(
            name="Example",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="auth-ref",
                allowed_targets=["example.test"],
            ),
        ),
    )


def test_scan_payload_ignores_receipt_timestamp():
    campaign = _campaign()
    first = policy_receipt(campaign, "example.test", "automated_scan")
    second = {**first, "timestamp": "2099-01-01T00:00:00+00:00"}

    first_payload = sanitized_scan_payload(campaign, first)
    second_payload = sanitized_scan_payload(campaign, second)

    assert first_payload == second_payload
    assert "timestamp" not in first_payload["policy"]
    assert first_payload["policy"]["authorization_reference"] == "auth-ref"


def test_scan_payload_preserves_policy_decision_fields():
    campaign = _campaign()
    receipt = policy_receipt(campaign, "example.test", "automated_scan")

    payload = sanitized_scan_payload(campaign, receipt)

    assert payload["policy"]["allowed"] is True
    assert payload["policy"]["scope_allowed"] is True
    assert payload["policy"]["action_blocked"] is False
    assert payload["policy"]["action"] == "automated_scan"
