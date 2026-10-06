from __future__ import annotations

from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.scanner_normalization import normalize_nuclei_item, normalize_strix_item, to_campaign_finding


def _campaign() -> Campaign:
    return Campaign(
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
            ),
        )
    )


def test_nuclei_cve_metadata_survives_normalization():
    normalized = normalize_nuclei_item(
        {
            "template-id": "CVE-2026-1207",
            "matcher-name": "postgres-error",
            "matched-at": "https://app.example.test/api?raster=1",
            "extracted-results": ["PostgreSQL 17.1"],
            "info": {
                "name": "Django RasterField - SQL Injection",
                "severity": "high",
                "description": "fixture",
                "impact": "SQL execution",
                "remediation": "upgrade",
                "reference": ["https://nvd.nist.gov/vuln/detail/CVE-2026-1207"],
                "tags": ["cve", "sqli", "kev"],
                "classification": {
                    "cvss-metrics": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:L",
                    "cvss-score": 8.1,
                    "cve-id": "CVE-2026-1207",
                    "epss-score": 0.12819,
                    "epss-percentile": 0.96182,
                    "cwe-id": "CWE-89",
                    "cpe": "cpe:2.3:a:djangoproject:django:*:*:*:*:*:*:*:*",
                },
                "metadata": {
                    "verified": True,
                    "max-request": 1,
                    "vendor": "djangoproject",
                    "product": "django",
                },
            },
        },
        _campaign(),
    )

    assert normalized is not None
    assert normalized.cve_ids == ("CVE-2026-1207",)
    assert normalized.cpe == ("cpe:2.3:a:djangoproject:django:*:*:*:*:*:*:*:*",)
    assert normalized.cvss == 8.1
    assert normalized.cvss_vector.startswith("CVSS:3.1/")
    assert normalized.epss_score == 0.12819
    assert normalized.epss_percentile == 0.96182
    assert normalized.template_verified is True
    assert normalized.template_max_requests == 1
    assert normalized.vendor == "djangoproject"
    assert normalized.product == "django"
    assert normalized.tags == ("cve", "sqli", "kev")
    assert normalized.impact == "SQL execution"
    assert normalized.remediation == "upgrade"

    finding = to_campaign_finding(normalized)
    assert finding.cve_ids == ["CVE-2026-1207"]
    assert finding.cpe == ["cpe:2.3:a:djangoproject:django:*:*:*:*:*:*:*:*"]
    assert finding.epss_score == 0.12819
    assert finding.epss_percentile == 0.96182
    assert finding.template_id == "CVE-2026-1207"
    assert finding.template_verified is True
    assert finding.template_max_requests == 1
    assert finding.references == ["https://nvd.nist.gov/vuln/detail/CVE-2026-1207"]
    assert finding.tags == ["cve", "sqli", "kev"]
    assert "cve-id:CVE-2026-1207" in finding.evidence


def test_strix_structured_metadata_is_bounded_and_persisted():
    normalized = normalize_strix_item(
        {
            "title": "Known vulnerability",
            "severity": "critical",
            "asset": "https://app.example.test",
            "cve_ids": ["CVE-2026-2222"],
            "cpe": ["cpe:2.3:a:vendor:product:1.2.3:*:*:*:*:*:*:*"],
            "cvss": 9.8,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            "epss_score": 0.9,
            "epss_percentile": 0.99,
            "references": ["https://example.test/advisory"],
            "tags": ["cve", "kev"],
            "template_verified": True,
            "template_max_requests": 2,
            "vendor": "vendor",
            "product": "product",
        },
        _campaign(),
    )

    assert normalized is not None
    finding = to_campaign_finding(normalized)
    assert finding.cve_ids == ["CVE-2026-2222"]
    assert finding.cpe == ["cpe:2.3:a:vendor:product:1.2.3:*:*:*:*:*:*:*"]
    assert finding.cvss_vector.startswith("CVSS:3.1/")
    assert finding.epss_score == 0.9
    assert finding.epss_percentile == 0.99
    assert finding.template_verified is True
    assert finding.template_max_requests == 2
    assert finding.vendor == "vendor"
    assert finding.product == "product"


def test_cve_metadata_defaults_keep_existing_findings_compatible():
    finding = Finding(
        title="legacy",
        severity="medium",
        asset="https://app.example.test",
        summary="legacy fixture",
    )

    assert finding.cve_ids == []
    assert finding.cpe == []
    assert finding.references == []
    assert finding.tags == []
    assert finding.template_verified is None
    assert finding.epss_score is None
