from types import SimpleNamespace

import app.hackerone_api as hackerone_api


def _program(handle: str):
    return {
        "handle": handle,
        "name": handle.upper(),
        "status": "REVIEW",
        "offers_bounties": True,
        "gold_standard_safe_harbor": True,
        "effort_factor": 1.0,
        "value_efficiency_score": 80,
        "opportunity_score": 80,
        "historical_usd_awarded_max": 1000,
        "historical_value_score": 50,
    }


def _selection(handles):
    items=[_program(handle) for handle in handles]
    return {
        "provider":"hackerone",
        "groups":{"easy":items[:2],"medium":items[2:4],"high_value":items[4:6]},
        "selection":items,
        "handles":handles,
        "complete":len(handles)==6,
        "selection_count":len(handles),
        "ready_count":0,
        "review_count":len(handles),
        "revalidation_count":0,
        "launch_ready":False,
        "catalog_source":"local-cache",
    }


def _snapshot(handle: str, *, complete: bool = True):
    domain=f"{handle}.example.com"
    return SimpleNamespace(
        handle=handle,
        snapshot_sha256=(handle[0] * 64)[:64],
        program={
            "name": handle.upper(),
            "offers_bounties": True,
            "gold_standard_safe_harbor": True,
            "submission_state": "open",
            "state": "public_mode",
            "policy": "Policy text",
        },
        document={"data": [], "links": {}},
        scope_exclusions=(),
        preview={
            "complete": complete,
            "assets": [
                {
                    "identifier": domain,
                    "asset_type": "Domain",
                    "eligible_for_submission": True,
                    "compatible": True,
                }
            ],
        },
    )


def test_review_package_stops_after_two_usable_programmes(monkeypatch):
    calls=[]

    def fake_fetch(handle):
        calls.append(handle)
        return _snapshot(handle, complete=handle in {"a","b"})

    monkeypatch.setattr(
        hackerone_api,
        "hackerone_simple_selection",
        lambda exclude="": _selection(["a","b","c","d","e","f"]),
    )
    monkeypatch.setattr(hackerone_api, "fetch_hackerone_program_snapshot", fake_fetch)

    result=hackerone_api.hackerone_simple_review_package()

    assert result["handles"] == ["a","b"]
    assert len(result["review_drafts"]) == 2
    assert result["review_package_target"] == 2
    assert result["review_package_minimum"] == 1
    assert set(calls).issuperset({"a","b"})


def test_review_package_returns_one_when_only_one_usable_programme_exists(monkeypatch):
    counter={"n":0}

    def fake_selection(exclude=""):
        counter["n"] += 1
        if counter["n"] == 1:
            return _selection(["a","b","c","d","e","f"])
        raise hackerone_api.HTTPException(
            status_code=409,
            detail={
                "reason":"simple_review_package_incomplete",
                "message":"done",
            },
        )

    monkeypatch.setattr(hackerone_api, "hackerone_simple_selection", fake_selection)
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(handle, complete=handle=="a"),
    )

    result=hackerone_api.hackerone_simple_review_package()

    assert result["handles"] == ["a"]
    assert len(result["review_drafts"]) == 1
    assert result["complete"] is True


def test_review_package_reports_failure_when_none_are_usable(monkeypatch):
    counter={"n":0}

    def fake_selection(exclude=""):
        counter["n"] += 1
        if counter["n"] == 1:
            return _selection(["a","b","c","d","e","f"])
        raise hackerone_api.HTTPException(
            status_code=409,
            detail={
                "reason":"simple_review_package_incomplete",
                "message":"done",
            },
        )

    monkeypatch.setattr(hackerone_api, "hackerone_simple_selection", fake_selection)
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(handle, complete=False),
    )

    try:
        hackerone_api.hackerone_simple_review_package()
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
        detail=getattr(exc, "detail", {})
        assert detail["reason"] == "simple_review_package_incomplete"
    else:
        raise AssertionError("zero usable programmes must fail closed")


def test_review_package_stops_on_global_hackerone_outage(monkeypatch):
    monkeypatch.setattr(
        hackerone_api,
        "hackerone_simple_selection",
        lambda exclude="": _selection(["a","b","c","d","e","f"]),
    )

    def fail_fetch(_handle):
        raise hackerone_api.HackerOneClientError(
            "temporary upstream failure",
            status_code=503,
        )

    monkeypatch.setattr(hackerone_api, "fetch_hackerone_program_snapshot", fail_fetch)

    try:
        hackerone_api.hackerone_simple_review_package()
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        detail=getattr(exc, "detail", {})
        assert detail["reason"] == "hackerone_upstream_unavailable"
        assert detail["contains_secrets"] is False
    else:
        raise AssertionError("global HackerOne outage must stop preparation")


def test_review_package_returns_one_or_two_usable_programmes(monkeypatch):
    def fake_selection(exclude=""):
        excluded={value for value in exclude.split(",") if value}
        handles=[h for h in ["a","b","c","d","e","f"] if h not in excluded]
        while len(handles)<6:
            handles.append("z"+str(len(handles)))
        return _selection(handles[:6])

    monkeypatch.setattr(hackerone_api, "hackerone_simple_selection", fake_selection)
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(handle, complete=handle in {"a","b"}),
    )

    result=hackerone_api.hackerone_simple_review_package()

    assert 1 <= len(result["handles"]) <= 2
    assert result["review_package_target"] == 2
    assert result["review_package_minimum"] == 1
    assert result["complete"] is True
