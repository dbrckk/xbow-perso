from app.main import Campaign, ProgramRules, TargetInput, is_host_allowed, policy_receipt, sanitized_scan_payload


def _campaign(**rule_overrides):
    rules = ProgramRules(
        authorization_reference="test-authorization",
        allowed_targets=["*.example.test", "example.test"],
        denied_targets=["admin.example.test"],
        **rule_overrides,
    )
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=rules,
        ),
    )


def test_deny_rules_override_allow_rules():
    campaign = _campaign()
    rules = campaign.target.rules

    assert is_host_allowed("api.example.test", rules.allowed_targets, rules.denied_targets) is True
    assert is_host_allowed("admin.example.test", rules.allowed_targets, rules.denied_targets) is False
    assert is_host_allowed("outside.test", rules.allowed_targets, rules.denied_targets) is False


def test_sensitive_actions_fail_closed_by_default():
    campaign = _campaign()

    for action in ("destructive", "dos", "social_engineering", "credential_attack"):
        receipt = policy_receipt(campaign, "example.test", action)
        assert receipt["allowed"] is False
        assert receipt["action_blocked"] is True
        assert receipt["scope_allowed"] is True


def test_out_of_scope_target_blocks_automated_scan():
    campaign = _campaign()
    receipt = policy_receipt(campaign, "outside.test", "automated_scan")

    assert receipt["allowed"] is False
    assert receipt["scope_allowed"] is False


def test_worker_payload_never_enables_prohibited_actions():
    campaign = _campaign(
        destructive_testing=True,
        denial_of_service=True,
        social_engineering=True,
        credential_attacks=True,
    )
    receipt = policy_receipt(campaign, "example.test", "automated_scan")
    payload = sanitized_scan_payload(campaign, receipt)

    assert payload["rules"]["destructive_testing"] is False
    assert payload["rules"]["denial_of_service"] is False
    assert payload["rules"]["social_engineering"] is False
    assert payload["rules"]["credential_attacks"] is False
