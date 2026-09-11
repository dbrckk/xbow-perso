import json

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.nuclei_parser import NucleiParserError, parse_nuclei_jsonl
from app.scanner_registry import parse_scanner_artifact, scanner_adapter, scanner_adapters
from app.scanner_normalization import (
    normalize_nuclei_item,
    normalize_strix_item,
    normalized_finding_id,
    to_campaign_finding,
)


def _campaign():
    return Campaign(
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
            ),
        )
    )


def test_strix_and_nuclei_normalize_to_same_canonical_shape():
    campaign = _campaign()
    strix = normalize_strix_item(
        {
            "title": "Fixture issue",
            "severity": "HIGH",
            "asset": "https://app.example.test",
            "endpoint": "https://app.example.test/profile",
            "description": "fixture",
            "cwe": "CWE-284",
        },
        campaign,
    )
    nuclei = normalize_nuclei_item(
        {
            "template-id": "fixture-template",
            "matched-at": "https://app.example.test/profile",
            "info": {
                "name": "Fixture issue",
                "severity": "high",
                "description": "fixture",
                "classification": {"cwe-id": ["CWE-284"]},
            },
        },
        campaign,
    )

    assert strix is not None
    assert nuclei is not None
    assert strix.severity == nuclei.severity == "high"
    assert strix.endpoint == nuclei.endpoint
    assert strix.cwe == nuclei.cwe == "CWE-284"
    assert to_campaign_finding(strix).status == "validation_required"
    assert to_campaign_finding(nuclei).status == "validation_required"


def test_normalized_ids_are_engine_scoped_and_stable():
    campaign = _campaign()
    item = normalize_strix_item(
        {
            "title": "Fixture issue",
            "asset": "https://app.example.test",
            "summary": "stable",
        },
        campaign,
    )
    assert item is not None

    first = normalized_finding_id(item)
    second = normalized_finding_id(item)

    assert first == second
    assert first.startswith("strix-")


def test_normalizers_fail_closed_outside_scope():
    campaign = _campaign()

    assert normalize_strix_item(
        {"title": "outside", "asset": "https://evil.invalid"},
        campaign,
    ) is None
    assert normalize_nuclei_item(
        {
            "template-id": "outside",
            "matched-at": "https://evil.invalid/path",
            "info": {"name": "outside"},
        },
        campaign,
    ) is None


def test_nuclei_jsonl_parser_normalizes_deduplicates_and_filters_scope(tmp_path):
    path = tmp_path / "nuclei.jsonl"
    item = {
        "template-id": "fixture-template",
        "matcher-name": "fixture-matcher",
        "matched-at": "https://app.example.test/profile?id=1",
        "extracted-results": ["fixture evidence"],
        "info": {
            "name": "Fixture issue",
            "severity": "medium",
            "description": "fixture",
            "classification": {
                "cwe-id": ["CWE-284"],
                "cvss-score": 6.5,
            },
        },
    }
    outside = {
        "template-id": "outside",
        "matched-at": "https://evil.invalid/",
        "info": {"name": "outside", "severity": "critical"},
    }
    path.write_text(
        "\n".join([json.dumps(item), json.dumps(item), json.dumps(outside)]),
        encoding="utf-8",
    )

    findings = parse_nuclei_jsonl(path, _campaign())

    assert len(findings) == 1
    finding = findings[0]
    assert finding.discovered_by == "nuclei"
    assert finding.severity == "medium"
    assert finding.cwe == "CWE-284"
    assert finding.cvss == 6.5
    assert finding.evidence == ["fixture evidence"]


def test_nuclei_jsonl_parser_rejects_invalid_line(tmp_path):
    path = tmp_path / "nuclei.jsonl"
    path.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        parse_nuclei_jsonl(path, _campaign())


def test_nuclei_jsonl_parser_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_MAX_NUCLEI_JSONL_BYTES", "1024")
    path = tmp_path / "nuclei.jsonl"
    path.write_text("x" * 1200, encoding="utf-8")

    with pytest.raises(NucleiParserError, match="size limit"):
        parse_nuclei_jsonl(path, _campaign())



def test_scanner_registry_exposes_supported_engines():
    adapters = scanner_adapters()

    assert [adapter.engine for adapter in adapters] == ["nuclei", "strix"]
    assert scanner_adapter("STRIX").format == "json"
    assert scanner_adapter("nuclei").format == "jsonl"


def test_scanner_registry_rejects_unknown_engine():
    with pytest.raises(ValueError, match="unsupported scanner engine"):
        scanner_adapter("unknown")


def test_scanner_registry_dispatches_strix_parser(tmp_path):
    path = tmp_path / "vulnerabilities.json"
    path.write_text(
        json.dumps(
            {
                "vulnerabilities": [
                    {
                        "title": "Registry fixture",
                        "severity": "low",
                        "asset": "https://app.example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    findings = parse_scanner_artifact("strix", path, _campaign())

    assert len(findings) == 1
    assert findings[0].discovered_by == "strix"


def test_scanner_registry_dispatches_nuclei_parser(tmp_path):
    path = tmp_path / "nuclei.jsonl"
    path.write_text(
        json.dumps(
            {
                "template-id": "registry-fixture",
                "matched-at": "https://app.example.test/profile",
                "info": {"name": "Registry fixture", "severity": "info"},
            }
        ),
        encoding="utf-8",
    )

    findings = parse_scanner_artifact("nuclei", path, _campaign())

    assert len(findings) == 1
    assert findings[0].discovered_by == "nuclei"
