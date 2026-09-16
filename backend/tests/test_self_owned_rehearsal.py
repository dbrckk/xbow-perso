from app.self_owned_rehearsal import (
    MANDATORY_SCENARIOS,
    ScenarioReferences,
    ScenarioResult,
    contains_raw_value,
    run_rehearsal,
)


def _pass(name: str) -> ScenarioResult:
    return ScenarioResult(
        name=name,
        status="pass",
        reason="invariant_satisfied",
        references=ScenarioReferences(),
    )


def test_run_rehearsal_requires_all_mandatory_scenarios():
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS}
    report = run_rehearsal(scenarios)
    assert report.status == "pass"
    assert [item.name for item in report.scenarios] == list(MANDATORY_SCENARIOS)
    assert report.external_network_used is False
    assert report.contains_secrets is False


def test_missing_scenario_fails_closed():
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS[:-1]}
    report = run_rehearsal(scenarios)
    assert report.status == "fail"
    assert report.scenarios[-1].name == MANDATORY_SCENARIOS[-1]
    assert report.scenarios[-1].reason == "scenario_missing"


def test_unexpected_exception_message_is_not_exposed():
    marker = "SECRET-MUST-NOT-LEAK"
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS}

    def explode():
        raise RuntimeError(marker)

    scenarios[MANDATORY_SCENARIOS[0]] = explode
    report = run_rehearsal(scenarios)
    assert report.scenarios[0].reason == "unexpected_RuntimeError"
    assert marker not in str(report)


def test_contains_raw_value_detects_nested_text_and_bytes():
    marker = "rehearsal-sentinel"
    assert contains_raw_value(marker, [{"nested": [b"xxrehearsal-sentinelxx"]}]) is True
    assert contains_raw_value(marker, [{"nested": ["[redacted]"]}]) is False
