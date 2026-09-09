import json

from app.main import Campaign, ProgramRules, TargetInput
from app.worker import WorkerPolicyError, locate_vulnerabilities_json, parse_strix_vulnerabilities


def campaign():
    return Campaign(
        target=TargetInput(
            name="local-test",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
            ),
        )
    )


def test_parser_normalizes_and_filters_scope(tmp_path):
    path = tmp_path / "vulnerabilities.json"
    path.write_text(
        json.dumps(
            {
                "vulnerabilities": [
                    {
                        "title": "Example access control issue",
                        "severity": "HIGH",
                        "asset": "https://app.example.test",
                        "endpoint": "/profile",
                        "technical_analysis": "Observed only in fixture data",
                        "poc_description": "Use the local fixture account",
                        "cwe": "CWE-284",
                    },
                    {
                        "title": "Out of scope",
                        "severity": "critical",
                        "asset": "https://evil.invalid",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    findings = parse_strix_vulnerabilities(path, campaign())
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].status == "validation_required"
    assert findings[0].discovered_by == "strix"
    assert findings[0].reproduction_steps == ["Use the local fixture account"]


def test_locator_rejects_symlink_escape(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"vulnerabilities": []}', encoding="utf-8")
    (run / "vulnerabilities.json").symlink_to(outside)
    assert locate_vulnerabilities_json(str(run)) is None


def test_parser_rejects_oversized_json(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_MAX_STRIX_JSON_BYTES", "1024")
    path = tmp_path / "vulnerabilities.json"
    path.write_text('{"vulnerabilities": [], "padding": "' + ("x" * 1200) + '"}', encoding="utf-8")
    try:
        parse_strix_vulnerabilities(path, campaign())
    except WorkerPolicyError as exc:
        assert "size limit" in str(exc)
    else:
        raise AssertionError("oversized Strix artifact must fail closed")


def test_invalid_strix_size_limit_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_MAX_STRIX_JSON_BYTES", "100")
    path = tmp_path / "vulnerabilities.json"
    path.write_text('{"vulnerabilities": []}', encoding="utf-8")
    try:
        parse_strix_vulnerabilities(path, campaign())
    except WorkerPolicyError as exc:
        assert "XBOW_MAX_STRIX_JSON_BYTES" in str(exc)
    else:
        raise AssertionError("unsafe artifact limit configuration must fail closed")
