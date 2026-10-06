import pytest

from app.active_validation import (
    SAFE_PROBE_PLAN_SCHEMA,
    ActiveValidationPlanError,
    analyze_cors_response,
    analyze_redirect_response,
    build_safe_probe_plan,
)


def test_disabled_plan_produces_zero_active_probes():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?id=secret",
    )

    assert plan.schema == SAFE_PROBE_PLAN_SCHEMA
    assert plan.enabled is False
    assert plan.probes == ()
    assert plan.automatic_execution_authorized is False
    assert plan.non_destructive_only is True
    assert plan.redirects_followed is False
    assert "secret" not in str(plan.to_dict())


def test_parameter_probes_mutate_only_existing_parameters():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?alpha=one&beta=two",
        enabled=True,
        parameter_validation_enabled=True,
        max_parameters=5,
        max_requests=8,
    )

    assert [probe.kind for probe in plan.probes] == [
        "baseline",
        "parameter_differential",
        "parameter_differential",
    ]
    assert [probe.parameter for probe in plan.probes[1:]] == [
        "alpha",
        "beta",
    ]
    assert all(probe.method == "GET" for probe in plan.probes)
    assert all(probe.marker.startswith("xbowv2-") for probe in plan.probes[1:])
    assert "one" not in str(plan.to_dict())
    assert "two" not in str(plan.to_dict())


def test_markers_are_deterministic_per_finding_and_parameter():
    first = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?id=one",
        enabled=True,
        parameter_validation_enabled=True,
    )
    second = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?id=two",
        enabled=True,
        parameter_validation_enabled=True,
    )

    assert first.probes[1].marker == second.probes[1].marker


def test_duplicate_parameter_names_are_planned_once():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?id=one&id=two&next=home",
        enabled=True,
        parameter_validation_enabled=True,
    )

    assert plan.parameter_names == ("id", "next")
    assert [probe.parameter for probe in plan.probes[1:]] == ["id", "next"]


def test_request_budget_includes_baseline_and_reports_skipped_probes():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?a=1&b=2&c=3",
        enabled=True,
        parameter_validation_enabled=True,
        cors_validation_enabled=True,
        max_requests=3,
    )

    assert len(plan.probes) == 3
    assert plan.probes[0].kind == "baseline"
    assert plan.skipped_probe_count == 2


def test_parameter_cap_is_enforced_before_budget():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?a=1&b=2&c=3",
        enabled=True,
        parameter_validation_enabled=True,
        max_parameters=2,
        max_requests=8,
    )

    assert [probe.parameter for probe in plan.probes[1:]] == ["a", "b"]


def test_cors_probe_uses_reserved_origin_header_without_external_request():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?id=one",
        enabled=True,
        cors_validation_enabled=True,
    )

    cors = next(probe for probe in plan.probes if probe.kind == "cors_origin")
    assert cors.request_url.startswith("https://example.test/")
    assert cors.headers == (("Origin", "https://xbow.invalid"),)
    assert all("xbow.invalid" not in probe.request_url for probe in plan.probes)


def test_redirect_probe_uses_exact_reserved_destination_and_never_follows_it():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/login?next=%2Fhome&other=x",
        enabled=True,
        redirect_validation_enabled=True,
    )

    redirect = next(
        probe for probe in plan.probes if probe.kind == "redirect_location"
    )
    assert redirect.parameter == "next"
    assert redirect.marker == "https://xbow.invalid/redirect-check"
    assert redirect.request_url.startswith("https://example.test/")
    assert plan.redirects_followed is False
    assert plan.automatic_execution_authorized is False


def test_non_redirect_parameter_does_not_get_redirect_probe():
    plan = build_safe_probe_plan(
        finding_id="f1",
        target_url="https://example.test/a?q=value",
        enabled=True,
        redirect_validation_enabled=True,
    )

    assert [probe.kind for probe in plan.probes] == ["baseline"]


@pytest.mark.parametrize(
    "url",
    (
        "ftp://example.test/a",
        "https://user:pass@example.test/a",
        "/relative",
        "",
    ),
)
def test_invalid_target_urls_fail_closed(url):
    with pytest.raises(ActiveValidationPlanError):
        build_safe_probe_plan(
            finding_id="f1",
            target_url=url,
            enabled=True,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_parameters", -1),
        ("max_parameters", 11),
        ("max_requests", 0),
        ("max_requests", 17),
    ),
)
def test_hard_caps_fail_closed(field, value):
    kwargs = {
        "finding_id": "f1",
        "target_url": "https://example.test/a?id=1",
        "enabled": True,
        field: value,
    }

    with pytest.raises(ActiveValidationPlanError):
        build_safe_probe_plan(**kwargs)



def test_cors_reflected_synthetic_origin_with_credentials_is_strong_review_signal():
    signal = analyze_cors_response(
        {
            "Access-Control-Allow-Origin": "https://xbow.invalid",
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    )

    assert signal.strength == "strong"
    assert signal.reason == "synthetic_origin_reflected_with_credentials"
    assert signal.exploitability_confirmed is False
    assert signal.evidence["vary_origin"] is True


def test_cors_wildcard_is_weak_not_confirmed():
    signal = analyze_cors_response(
        {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )

    assert signal.strength == "weak"
    assert signal.reason == "wildcard_origin_observed"
    assert signal.exploitability_confirmed is False


def test_absent_cors_headers_yield_no_signal():
    signal = analyze_cors_response({})

    assert signal.strength == "none"
    assert signal.reason == "no_cors_signal"


def test_redirect_requires_exact_reserved_destination():
    signal = analyze_redirect_response(
        http_status=302,
        location="https://xbow.invalid/redirect-check",
        parameter="next",
    )

    assert signal.strength == "strong"
    assert signal.reason == "exact_reserved_destination_returned"
    assert signal.parameter == "next"
    assert signal.exploitability_confirmed is False


@pytest.mark.parametrize(
    "location",
    (
        "https://xbow.invalid/redirect-check.evil",
        "https://xbow.invalid.evil/redirect-check",
        "/redirect-check",
        "https://xbow.invalid/redirect-check?extra=1",
        "https://xbow.invalid/redirect-check#fragment",
    ),
)
def test_redirect_substring_or_non_exact_locations_do_not_promote(location):
    signal = analyze_redirect_response(
        http_status=302,
        location=location,
        parameter="next",
    )

    assert signal.strength == "none"
    assert signal.evidence["location_exact_reserved_match"] is False


def test_redirect_non_3xx_status_never_promotes():
    signal = analyze_redirect_response(
        http_status=200,
        location="https://xbow.invalid/redirect-check",
        parameter="next",
    )

    assert signal.strength == "none"
