from types import SimpleNamespace

from app.cpe_consistency import (
    CPE_CONSISTENCY_SCHEMA,
    build_cpe_consistency,
)
from app.cve_risk_context import build_cve_risk_context


def _finding(*, product="django", cpe=None):
    return SimpleNamespace(
        id="f1",
        product=product,
        cpe=list(cpe or []),
        cve_ids=["CVE-2026-12345"],
        evidence=["cve-id:CVE-2026-12345"],
        title="fixture",
        summary="",
        cvss=None,
        epss_score=None,
        epss_percentile=None,
        template_verified=False,
        tags=[],
    )


def test_matching_cpe_supports_product_identity():
    finding = _finding(
        cpe=["cpe:2.3:a:djangoproject:django:5.1:*:*:*:*:*:*:*"]
    )

    result = build_cpe_consistency(finding)

    assert result.schema == CPE_CONSISTENCY_SCHEMA
    assert result.cpe_supports_product_identity is True
    assert result.product_match_count == 1
    assert result.reasons == ()


def test_generic_cpe_does_not_support_product_identity():
    finding = _finding(
        cpe=["cpe:2.3:a:djangoproject:*:*:*:*:*:*:*:*:*"]
    )

    result = build_cpe_consistency(finding)

    assert result.cpe_supports_product_identity is False
    assert result.reasons == ("generic_cpe_product",)


def test_mismatched_cpe_is_explicitly_flagged():
    finding = _finding(
        product="django",
        cpe=["cpe:2.3:a:apache:http_server:2.4.62:*:*:*:*:*:*:*"],
    )

    result = build_cpe_consistency(finding)

    assert result.cpe_supports_product_identity is False
    assert result.mismatch_count == 1
    assert result.reasons == ("cpe_product_mismatch",)


def test_unparseable_cpe_is_not_trusted():
    finding = _finding(cpe=["not-a-cpe"])

    result = build_cpe_consistency(finding)

    assert result.cpe_supports_product_identity is False
    assert result.reasons == ("unparseable_cpe",)


def test_risk_context_only_rewards_consistent_cpe():
    matching = build_cve_risk_context(
        _finding(
            cpe=["cpe:2.3:a:djangoproject:django:5.1:*:*:*:*:*:*:*"]
        )
    )
    mismatched = build_cve_risk_context(
        _finding(
            cpe=["cpe:2.3:a:apache:http_server:2.4.62:*:*:*:*:*:*:*"]
        )
    )

    assert matching.cpe_supports_product_identity is True
    assert "cpe_product_consistent" in matching.reasons
    assert mismatched.cpe_supports_product_identity is False
    assert "cpe_untrusted" in mismatched.reasons
    assert matching.risk_score > mismatched.risk_score


def test_matching_cpe_version_supports_version_identity():
    finding = _finding(
        cpe=["cpe:2.3:a:djangoproject:django:5.1.2:*:*:*:*:*:*:*"]
    )

    result = build_cpe_consistency(
        finding,
        observed_versions=("5.1.2",),
    )

    assert result.cpe_supports_product_identity is True
    assert result.cpe_supports_version_identity is True
    assert result.version_match_count == 1
    assert result.version_mismatch_count == 0


def test_mismatched_cpe_version_is_flagged():
    finding = _finding(
        cpe=["cpe:2.3:a:djangoproject:django:4.2.0:*:*:*:*:*:*:*"]
    )

    result = build_cpe_consistency(
        finding,
        observed_versions=("5.1.2",),
    )

    assert result.cpe_supports_product_identity is True
    assert result.cpe_supports_version_identity is False
    assert result.version_mismatch_count == 1
    assert "cpe_version_mismatch" in result.reasons


def test_generic_cpe_version_never_claims_version_identity():
    finding = _finding(
        cpe=["cpe:2.3:a:djangoproject:django:*:*:*:*:*:*:*:*"]
    )

    result = build_cpe_consistency(
        finding,
        observed_versions=("5.1.2",),
    )

    assert result.cpe_supports_product_identity is True
    assert result.cpe_supports_version_identity is False
    assert result.generic_version_count == 1
    assert "generic_cpe_version" in result.reasons


def test_without_observed_version_cpe_version_is_not_guessed():
    finding = _finding(
        cpe=["cpe:2.3:a:djangoproject:django:5.1.2:*:*:*:*:*:*:*"]
    )

    result = build_cpe_consistency(finding)

    assert result.cpe_supports_product_identity is True
    assert result.cpe_supports_version_identity is False
    assert result.version_match_count == 0
    assert result.version_mismatch_count == 0
