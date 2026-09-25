import pytest

from app.hackerone_scope_import import (
    HackerOneProgramPolicy,
    HackerOneScopeImportError,
    import_hackerone_structured_scope,
    project_hackerone_exact_domain_scope,
)


def _resource(
    identifier: str,
    asset_type: str,
    eligible: bool,
    *,
    resource_type: str = "structured-scope",
):
    return {
        "type": resource_type,
        "id": f"{asset_type}:{identifier}",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": asset_type,
            "eligible_for_submission": eligible,
            "eligible_for_bounty": eligible,
            "instruction": None,
        },
    }


def _policy(**overrides):
    values = {
        "authorization_reference": "H1-PROGRAM-42",
        "policy_version": "2026-09-15",
        "reviewed_at": "2026-09-15T20:00:00+02:00",
        "reviewed_by": "human-reviewer",
        "safe_harbor_confirmed": True,
        "automated_scanning": False,
        "max_requests_per_second": 1.0,
        "test_account_required": False,
        "test_account_constraints": "",
        "additional_restrictions": (),
        "program_notes": "Reviewed against the current HackerOne program policy.",
    }
    values.update(overrides)
    return HackerOneProgramPolicy(**values)


def test_hackerone_scope_preview_maps_host_safe_assets():
    document = {
        "data": [
            _resource("Example.COM.", "Domain", True),
            _resource("*.api.example.com", "Wildcard", True),
            _resource("192.0.2.10", "IpAddress", True),
            _resource("blocked.example.com", "Domain", False),
        ]
    }

    preview = import_hackerone_structured_scope(document)

    assert preview.complete is True
    assert preview.allowed_targets == (
        "*.api.example.com",
        "192.0.2.10",
        "example.com",
    )
    assert preview.denied_targets == ("blocked.example.com",)
    assert preview.conflicts == ()
    assert preview.unsupported == ()
    assert all(asset.compatible for asset in preview.assets)
    assert [asset.eligible_for_bounty for asset in preview.assets] == [
        True,
        True,
        True,
        False,
    ]


def test_hackerone_scope_conversion_requires_explicit_program_policy():
    preview = import_hackerone_structured_scope(
        {"data": [_resource("example.com", "Domain", True)]}
    )
    policy = _policy(max_requests_per_second=1.25)

    rules = preview.to_program_rules(policy=policy)

    assert rules.authorization_reference == "H1-PROGRAM-42"
    assert rules.allowed_targets == ["example.com"]
    assert rules.denied_targets == []
    assert rules.max_requests_per_second == 1.25
    assert rules.automated_scanning is False
    assert rules.destructive_testing is False
    assert rules.denial_of_service is False
    assert rules.social_engineering is False
    assert rules.credential_attacks is False
    assert "explicit HackerOne program policy" in rules.notes


def test_hackerone_policy_snapshot_is_normalized_and_complete():
    policy = _policy(
        test_account_required=True,
        test_account_constraints="Use the program-issued test tenant only.",
        additional_restrictions=("No production data access", "No production data access"),
    )

    assert policy.to_snapshot() == {
        "authorization_reference": "H1-PROGRAM-42",
        "policy_version": "2026-09-15",
        "reviewed_at": "2026-09-15T18:00:00+00:00",
        "reviewed_by": "human-reviewer",
        "safe_harbor_confirmed": True,
        "automated_scanning": False,
        "max_requests_per_second": 1.0,
        "test_account_required": True,
        "test_account_constraints": "Use the program-issued test tenant only.",
        "additional_restrictions": ["No production data access"],
        "program_notes": "Reviewed against the current HackerOne program policy.",
    }


def test_hackerone_policy_can_explicitly_allow_automated_scanning():
    preview = import_hackerone_structured_scope(
        {"data": [_resource("example.com", "Domain", True)]}
    )
    policy = _policy(automated_scanning=True, max_requests_per_second=0.5)

    rules = preview.to_program_rules(policy=policy)

    assert rules.automated_scanning is True
    assert rules.max_requests_per_second == 0.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"authorization_reference": ""},
        {"policy_version": ""},
        {"reviewed_at": "2026-09-15T20:00:00"},
        {"reviewed_by": ""},
        {"safe_harbor_confirmed": "yes"},
        {"automated_scanning": "yes"},
        {"max_requests_per_second": 0},
        {"max_requests_per_second": 21},
        {"test_account_required": "no"},
        {
            "test_account_required": True,
            "test_account_constraints": "",
        },
        {"additional_restrictions": ("",)},
    ],
)
def test_invalid_hackerone_program_policy_fails_closed(kwargs):
    with pytest.raises(HackerOneScopeImportError):
        _policy(**kwargs)


@pytest.mark.parametrize(
    ("identifier", "asset_type", "reason"),
    [
        (
            "https://example.com/admin",
            "Url",
            "url_scope_requires_scheme_path_aware_policy",
        ),
        ("192.0.2.0/24", "Cidr", "cidr_requires_network_aware_policy"),
        (
            "com.example.mobile",
            "AndroidPlayStore",
            "asset_type_not_supported_by_web_scope_engine",
        ),
    ],
)
def test_unsupported_scope_assets_block_rule_conversion(identifier, asset_type, reason):
    preview = import_hackerone_structured_scope(
        {"data": [_resource(identifier, asset_type, True)]}
    )

    assert preview.complete is False
    assert preview.assets[0].compatible is False
    assert preview.assets[0].reason == reason
    assert preview.unsupported == (f"{asset_type}:{identifier}",)

    with pytest.raises(HackerOneScopeImportError, match="cannot be converted"):
        preview.to_program_rules(policy=_policy(authorization_reference="AUTH-1"))


def test_out_of_scope_unsupported_asset_also_blocks_conversion():
    document = {
        "data": [
            _resource("*.example.com", "Wildcard", True),
            _resource("https://example.com/private", "Url", False),
        ]
    }

    preview = import_hackerone_structured_scope(document)

    assert preview.complete is False
    assert preview.allowed_targets == ("*.example.com",)
    with pytest.raises(HackerOneScopeImportError, match="cannot be converted"):
        preview.to_program_rules(policy=_policy(authorization_reference="AUTH-1"))


def test_conflicting_scope_entries_fail_closed():
    document = {
        "data": [
            _resource("example.com", "Domain", True),
            _resource("EXAMPLE.COM", "domain", False),
        ]
    }

    preview = import_hackerone_structured_scope(document)

    assert preview.complete is False
    assert preview.conflicts == ("example.com",)
    assert preview.denied_targets == ("example.com",)
    assert preview.allowed_targets == ()
    with pytest.raises(HackerOneScopeImportError, match="cannot be converted"):
        preview.to_program_rules(policy=_policy(authorization_reference="AUTH-1"))


def test_duplicate_same_scope_entries_are_deduplicated():
    document = {
        "data": [
            _resource("example.com", "Domain", True),
            _resource("EXAMPLE.COM.", "domain", True),
        ]
    }

    preview = import_hackerone_structured_scope(document)

    assert preview.complete is True
    assert preview.allowed_targets == ("example.com",)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"data": "not-a-resource"},
        {"data": [{"type": "wrong", "attributes": {}}]},
        {
            "data": [
                {
                    "type": "structured-scope",
                    "attributes": {
                        "asset_identifier": "example.com",
                        "asset_type": "Domain",
                        "eligible_for_submission": "true",
                    },
                }
            ]
        },
    ],
)
def test_malformed_hackerone_scope_fails_closed(document):
    with pytest.raises(HackerOneScopeImportError):
        import_hackerone_structured_scope(document)


@pytest.mark.parametrize(
    ("identifier", "asset_type"),
    [
        ("https://user:pass@example.com", "Url"),
        ("bad domain.example", "Domain"),
        ("*.*.example.com", "Wildcard"),
        ("999.999.999.999", "IpAddress"),
    ],
)
def test_invalid_identifiers_never_become_allowed_targets(identifier, asset_type):
    preview = import_hackerone_structured_scope(
        {"data": [_resource(identifier, asset_type, True)]}
    )

    assert preview.complete is False
    assert preview.allowed_targets == ()
    assert preview.assets[0].compatible is False


@pytest.mark.parametrize(
    "identifier",
    [
        "http://[",
        "https://[::1",
        "https://user:pass@[",
    ],
)
def test_malformed_urls_never_escape_parser_errors(identifier):
    preview = import_hackerone_structured_scope(
        {"data": [_resource(identifier, "Url", True)]}
    )

    assert preview.complete is False
    assert preview.allowed_targets == ()
    assert preview.assets[0].compatible is False
    assert preview.assets[0].reason == "invalid_url"
    assert preview.unsupported == (f"Url:{identifier}",)


def test_scope_asset_limit_fails_closed():
    document = {
        "data": [
            _resource(f"host-{index}.example.com", "Domain", True)
            for index in range(5001)
        ]
    }

    with pytest.raises(HackerOneScopeImportError, match="5000 asset safety limit"):
        import_hackerone_structured_scope(document)


def test_paginated_scope_page_fails_closed():
    document = {
        "data": [_resource("example.com", "Domain", True)],
        "links": {
            "next": "https://api.hackerone.com/v1/programs/1/structured_scopes?page[number]=2"
        },
    }

    with pytest.raises(HackerOneScopeImportError, match="collect all pages before import"):
        import_hackerone_structured_scope(document)


@pytest.mark.parametrize("links", [{}, {"next": None}, {"next": ""}])
def test_terminal_scope_page_is_accepted(links):
    preview = import_hackerone_structured_scope(
        {
            "data": [_resource("example.com", "Domain", True)],
            "links": links,
        }
    )

    assert preview.complete is True
    assert preview.allowed_targets == ("example.com",)


def test_malformed_scope_links_fail_closed():
    with pytest.raises(HackerOneScopeImportError, match="links are invalid"):
        import_hackerone_structured_scope(
            {
                "data": [_resource("example.com", "Domain", True)],
                "links": ["not", "a", "mapping"],
            }
        )


def test_exact_domain_projection_ignores_unrelated_unsupported_assets():
    document = {
        "data": [
            _resource("web.example.com", "Domain", True),
            _resource("com.example.mobile", "AndroidPlayStore", True),
            _resource("https://other.example.com/private", "Url", False),
        ]
    }

    projection = project_hackerone_exact_domain_scope(
        document,
        "https://web.example.com",
    )
    preview = import_hackerone_structured_scope(projection)

    assert preview.complete is True
    assert preview.allowed_targets == ("web.example.com",)
    assert preview.denied_targets == ()
    assert len(projection["data"]) == 1


def test_exact_domain_projection_fails_on_exact_denial():
    document = {
        "data": [
            _resource("web.example.com", "Domain", True),
            _resource("WEB.EXAMPLE.COM", "Domain", False),
        ]
    }

    with pytest.raises(
        HackerOneScopeImportError,
        match="explicit out-of-scope",
    ):
        project_hackerone_exact_domain_scope(
            document,
            "https://web.example.com",
        )


def test_exact_domain_projection_fails_on_denied_covering_wildcard():
    document = {
        "data": [
            _resource("web.example.com", "Domain", True),
            _resource("*.example.com", "Wildcard", False),
        ]
    }

    with pytest.raises(
        HackerOneScopeImportError,
        match="explicit out-of-scope",
    ):
        project_hackerone_exact_domain_scope(
            document,
            "https://web.example.com",
        )


def test_exact_domain_projection_requires_exact_eligible_domain():
    document = {
        "data": [
            _resource("*.example.com", "Wildcard", True),
            _resource("com.example.mobile", "AndroidPlayStore", True),
        ]
    }

    with pytest.raises(
        HackerOneScopeImportError,
        match="exact eligible HackerOne Domain",
    ):
        project_hackerone_exact_domain_scope(
            document,
            "https://web.example.com",
        )
