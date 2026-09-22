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


def test_atomic_review_package_caches_valid_drafts_across_server_replacement(monkeypatch):
    calls=[]

    def fake_selection(exclude=""):
        excluded={value for value in exclude.split(",") if value}
        return _selection(
            ["a","b","c","d","e","g"]
            if "f" in excluded
            else ["a","b","c","d","e","f"]
        )

    def fake_fetch(handle):
        calls.append(handle)
        return _snapshot(handle, complete=handle!="f")

    monkeypatch.setattr(hackerone_api, "hackerone_simple_selection", fake_selection)
    monkeypatch.setattr(hackerone_api, "fetch_hackerone_program_snapshot", fake_fetch)

    result=hackerone_api.hackerone_simple_review_package()

    assert result["handles"] == ["a","b","c","d","e","g"]
    assert [draft["handle"] for draft in result["review_drafts"]] == ["a","b","c","d","e","g"]
    assert result["review_package_rounds"] == 2
    assert result["review_package_rejected"] == 1
    assert calls.count("a") == 1
    assert calls.count("b") == 1
    assert calls.count("c") == 1
    assert calls.count("d") == 1
    assert calls.count("e") == 1
    assert calls.count("f") == 1
    assert calls.count("g") == 1


def test_atomic_review_package_reports_bounded_failure(monkeypatch):
    counter={"n":0}

    def fake_selection(exclude=""):
        counter["n"] += 1
        base=counter["n"] * 10
        return _selection([f"x{base+i}" for i in range(6)])

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
        assert detail["reason"] == "simple_review_package_exhausted"
        assert detail["contains_secrets"] is False
    else:
        raise AssertionError("exhausted review package must fail closed")
