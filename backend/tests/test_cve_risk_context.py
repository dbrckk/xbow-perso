from types import SimpleNamespace

from app.kev_catalog import build_kev_catalog

from app.cve_risk_context import (
    CVE_RISK_CONTEXT_SCHEMA,
    build_cve_risk_context,
)


def _finding(**overrides):
    values = {
        "id": "f1",
        "cve_ids": ["CVE-2026-12345"],
        "evidence": ["cve-id:CVE-2026-12345"],
        "title": "fixture",
        "summary": "",
        "cvss": 9.8,
        "epss_score": 0.8,
        "epss_percentile": 0.99,
        "cpe": ["cpe:2.3:a:vendor:product:1.2.3:*:*:*:*:*:*:*"],
        "template_verified": True,
        "tags": ["cve", "kev"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_risk_context_combines_structured_cve_metadata_without_confirmation():
    result = build_cve_risk_context(_finding())

    assert result.schema == CVE_RISK_CONTEXT_SCHEMA
    assert result.risk_band == "critical_priority"
    assert result.risk_score >= 0.75
    assert result.scanner_tagged_kev is True
    assert result.authoritative_kev_verified is False
    assert "scanner_tagged_kev_unverified" in result.reasons
    assert result.exploitability_confirmed is False


def test_scanner_kev_tag_never_becomes_authoritative_automatically():
    result = build_cve_risk_context(_finding(tags=["kev"]))

    assert result.scanner_tagged_kev is True
    assert result.authoritative_kev_verified is False
    assert "authoritative_kev_verified" not in result.reasons


def test_explicit_authoritative_kev_verification_is_distinct():
    result = build_cve_risk_context(
        _finding(tags=[]),
        authoritative_kev_verified=True,
    )

    assert result.scanner_tagged_kev is False
    assert result.authoritative_kev_verified is True
    assert "authoritative_kev_verified" in result.reasons


def test_non_cve_finding_is_not_ranked_as_cve_risk():
    finding = _finding(
        cve_ids=[],
        evidence=[],
        title="behavioral anomaly",
        cvss=9.8,
        epss_score=0.9,
        epss_percentile=0.99,
        tags=["kev"],
    )

    result = build_cve_risk_context(finding)

    assert result.risk_score == 0.0
    assert result.risk_band == "not_applicable"
    assert result.exploitability_confirmed is False


def test_missing_external_metrics_remains_usable_and_conservative():
    result = build_cve_risk_context(
        _finding(
            cvss=None,
            epss_score=None,
            epss_percentile=None,
            cpe=[],
            template_verified=None,
            tags=[],
        )
    )

    assert result.risk_score == 0.0
    assert result.risk_band == "low_priority"
    assert result.reasons == ()


def test_invalid_metric_values_are_ignored():
    result = build_cve_risk_context(
        _finding(
            cvss=99,
            epss_score=2,
            epss_percentile=-1,
            tags=[],
        )
    )

    assert result.cvss is None
    assert result.epss_score is None
    assert result.epss_percentile is None
    assert result.exploitability_confirmed is False


def test_verified_kev_catalog_promotes_only_matching_cve():
    catalog = build_kev_catalog(
        {
            "catalogVersion": "fixture",
            "dateReleased": "2026-10-06",
            "count": 1,
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-12345",
                    "vendorProject": "Vendor",
                    "product": "Product",
                    "dateAdded": "2026-10-01",
                    "dueDate": "2026-10-20",
                    "knownRansomwareCampaignUse": "Unknown",
                }
            ],
        },
        source_verified=True,
    )

    matched = build_cve_risk_context(
        _finding(cve_ids=["CVE-2026-12345"]),
        kev_catalog=catalog,
    )
    unmatched = build_cve_risk_context(
        _finding(
            cve_ids=["CVE-2026-99999"],
            evidence=["cve-id:CVE-2026-99999"],
        ),
        kev_catalog=catalog,
    )

    assert matched.authoritative_kev_verified is True
    assert "authoritative_kev_verified" in matched.reasons
    assert unmatched.authoritative_kev_verified is False


def test_unverified_kev_catalog_cannot_promote_risk_context():
    catalog = build_kev_catalog(
        {
            "catalogVersion": "fixture",
            "dateReleased": "2026-10-06",
            "count": 1,
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-12345",
                    "vendorProject": "Vendor",
                    "product": "Product",
                    "dateAdded": "2026-10-01",
                    "dueDate": "2026-10-20",
                    "knownRansomwareCampaignUse": "Known",
                }
            ],
        },
        source_verified=False,
    )

    result = build_cve_risk_context(
        _finding(),
        kev_catalog=catalog,
    )

    assert result.authoritative_kev_verified is False
    assert "authoritative_kev_verified" not in result.reasons
