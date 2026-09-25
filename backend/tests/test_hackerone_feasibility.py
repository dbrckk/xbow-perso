from types import SimpleNamespace

import app.hackerone_feasibility as feasibility
from app.simple_portfolio import select_simple_six


class _Store:
    def __init__(self, catalog):
        self.catalog = dict(catalog)
        self.version = 1

    def get_hackerone_catalog_state_record(self, catalog_id="current"):
        return dict(self.catalog), self.version

    def get_hackerone_catalog_state(self, catalog_id="current"):
        return dict(self.catalog)

    def save_hackerone_catalog_state(self, document, *, expected_version=None):
        assert expected_version == self.version
        self.catalog = dict(document)
        self.version += 1
        return self.version


def _program(handle: str):
    return {
        "handle": handle,
        "name": handle.upper(),
        "submission_state": "open",
        "state": "public_mode",
        "offers_bounties": True,
        "gold_standard_safe_harbor": True,
    }


def _snapshot(handle: str, *, compatible: bool = True):
    domain = f"{handle}.example.com"
    return SimpleNamespace(
        handle=handle,
        snapshot_sha256=(handle[0] * 64)[:64],
        program={
            "name": handle.upper(),
            "offers_bounties": True,
            "gold_standard_safe_harbor": True,
            "submission_state": "open",
            "state": "public_mode",
            "policy": "Automated security testing is permitted within the programme scope.",
        },
        document={
            "data": [
                {
                    "type": "structured-scope",
                    "attributes": {
                        "asset_identifier": domain,
                        "asset_type": "Domain",
                        "eligible_for_submission": True,
                    },
                }
            ],
            "links": {},
        },
        scope_exclusions=(),
        preview={
            "complete": compatible,
            "assets": [
                {
                    "identifier": domain,
                    "asset_type": "Domain",
                    "eligible_for_submission": True,
                    "compatible": compatible,
                }
            ],
        },
    )


def _ranked(handle: str, *, compatible):
    return {
        "handle": handle,
        "name": handle,
        "status": "REVIEW",
        "offers_bounties": True,
        "gold_standard_safe_harbor": True,
        "effort_factor": 1.0,
        "value_efficiency_score": 80,
        "opportunity_score": 80,
        "historical_usd_awarded_max": 1000,
        "historical_value_score": 50,
        "project_compatible": compatible,
    }


def test_feasibility_batch_builds_durable_compatible_index(monkeypatch):
    catalog = {
        "id": "current",
        "programs": [_program("alpha"), _program("beta")],
        "fingerprint": "f" * 64,
        "checked_at": "2026-09-25T00:00:00+00:00",
        "updated_at": "2026-09-25T00:00:00+00:00",
    }
    store = _Store(catalog)

    def fake_fetch(handle):
        return _snapshot(handle, compatible=handle == "alpha")

    monkeypatch.setattr(feasibility, "fetch_hackerone_program_snapshot", fake_fetch)

    result = feasibility.refresh_hackerone_feasibility_batch(store, batch_size=2)

    assert result["status"] == "refreshed"
    assert result["checked"] == 2
    assert result["compatible"] == 1
    index = store.catalog["feasibility_index"]
    assert index["alpha"]["project_compatible"] is True
    assert index["alpha"]["primary_url"] == "https://alpha.example.com"
    assert index["beta"]["project_compatible"] is False
    assert index["beta"]["blockers"]


def test_feasibility_summary_lists_many_compatible_programmes():
    catalog = {
        "feasibility_index": {
            "alpha": {
                "project_compatible": True,
                "status": "compatible",
                "primary_url": "https://alpha.example.com",
                "scope_mode": "full",
                "checked_at": "2026-09-25T00:00:00+00:00",
                "snapshot_sha256": "a" * 64,
            },
            "beta": {
                "project_compatible": False,
                "status": "blocked",
                "blockers": ["scope_incomplete_for_web_engine"],
                "checked_at": "2026-09-25T00:00:00+00:00",
            },
        },
        "programs": [_program("alpha"), _program("beta")],
        "feasibility_updated_at": "2026-09-25T00:00:00+00:00",
    }

    result = feasibility.feasibility_summary(catalog)

    assert result["indexed"] == 2
    assert result["compatible_count"] == 1
    assert result["blocked_count"] == 1
    assert result["programs"][0]["handle"] == "alpha"
    assert result["blocker_counts"]["scope_incomplete_for_web_engine"] == 1
    assert result["automatic_launch"] is False
    assert result["scope_expansion"] is False


def test_simple_portfolio_prefers_known_project_compatible_programmes():
    programs = [
        _ranked("unknown-a", compatible=None),
        _ranked("unknown-b", compatible=None),
        _ranked("compatible-a", compatible=True),
        _ranked("compatible-b", compatible=True),
        _ranked("compatible-c", compatible=True),
        _ranked("compatible-d", compatible=True),
        _ranked("compatible-e", compatible=True),
        _ranked("compatible-f", compatible=True),
    ]

    result = select_simple_six(programs)

    assert result["complete"] is True
    assert all(
        item["project_compatible"] is True
        for item in result["selection"]
    )
    assert result["project_feasibility_preferred"] is True


def test_feasibility_route_is_exposed():
    from app.main import app

    schema = app.openapi()
    assert "/api/hackerone/feasibility-index" in schema["paths"]


def test_worker_continuously_builds_feasibility_index():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app" / "worker_service.py"
    ).read_text(encoding="utf-8")
    assert "maybe_refresh_hackerone_feasibility" in source
    assert "maybe_refresh_hackerone_feasibility(store)" in source


def test_initial_feasibility_warmup_checks_twelve_programmes(monkeypatch):
    programs = [_program(f"p{i:02d}") for i in range(20)]
    store = _Store({
        "id": "current",
        "programs": programs,
        "fingerprint": "f" * 64,
        "checked_at": "2026-09-25T00:00:00+00:00",
        "updated_at": "2026-09-25T00:00:00+00:00",
    })
    seen=[]

    def fake_fetch(handle):
        seen.append(handle)
        return _snapshot(handle, compatible=True)

    monkeypatch.setattr(feasibility, "fetch_hackerone_program_snapshot", fake_fetch)

    result = feasibility.refresh_hackerone_feasibility_batch(store)

    assert result["checked"] == 12
    assert len(seen) == 12


def test_retryable_hackerone_failure_is_not_cached_as_incompatible(monkeypatch):
    store = _Store({
        "id": "current",
        "programs": [_program("alpha")],
        "fingerprint": "f" * 64,
        "checked_at": "2026-09-25T00:00:00+00:00",
        "updated_at": "2026-09-25T00:00:00+00:00",
    })

    def fail(_handle):
        raise feasibility.HackerOneClientError("rate limited", status_code=429)

    monkeypatch.setattr(feasibility, "fetch_hackerone_program_snapshot", fail)

    feasibility.refresh_hackerone_feasibility_batch(store, batch_size=1)

    record = store.catalog["feasibility_index"]["alpha"]
    assert record["project_compatible"] is None
    assert record["retryable"] is True
    summary = feasibility.feasibility_summary(store.catalog)
    assert summary["blocked_count"] == 0
    assert summary["unavailable_count"] == 1


def test_retryable_entries_are_prioritized_for_recheck():
    existing = {
        "alpha": {
            "retryable": True,
            "checked_at": "2026-09-25T00:00:00+00:00",
        },
        "beta": {
            "retryable": False,
            "checked_at": "2026-09-24T00:00:00+00:00",
        },
    }

    assert feasibility._checked_sort_key("alpha", existing)[0] == 0
    assert feasibility._checked_sort_key("beta", existing)[0] == 1
