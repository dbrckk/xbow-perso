import app.hackerone_catalog as catalog
from app.storage import Storage


class FakeClient:
    def __init__(self, programs):
        self.programs = programs

    def get_all_pages(self, path):
        assert path == "hackers/programs"
        return self.programs


def _resource(
    handle,
    name,
    *,
    bounty=True,
    safe_harbor=True,
    submission_state="open",
    state="public_mode",
):
    return {
        "type": "program",
        "attributes": {
            "handle": handle,
            "name": name,
            "submission_state": submission_state,
            "state": state,
            "offers_bounties": bounty,
            "gold_standard_safe_harbor": safe_harbor,
            "policy": "must never enter the catalog",
        },
    }


def test_catalog_initial_refresh_is_redacted_and_persisted(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    result = catalog.refresh_hackerone_catalog(
        store,
        client=FakeClient([_resource("acme", "Acme")]),
    )

    assert result["change_sequence"] == 0
    assert result["changes"] == {"added": [], "removed": [], "changed": []}
    assert result["programs"] == [
        {
            "handle": "acme",
            "name": "Acme",
            "submission_state": "open",
            "state": "public_mode",
            "offers_bounties": True,
            "gold_standard_safe_harbor": True,
        }
    ]
    assert "policy" not in result["programs"][0]
    assert store.get_hackerone_catalog_state()["fingerprint"] == result["fingerprint"]


def test_catalog_detects_added_removed_and_changed_programs(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    catalog.refresh_hackerone_catalog(
        store,
        client=FakeClient(
            [
                _resource("one", "One", bounty=True),
                _resource("two", "Two", bounty=False),
            ]
        ),
    )

    result = catalog.refresh_hackerone_catalog(
        store,
        client=FakeClient(
            [
                _resource("one", "One", bounty=False),
                _resource("three", "Three", bounty=True),
            ]
        ),
    )

    assert result["change_sequence"] == 1
    assert result["changes"] == {
        "added": ["three"],
        "removed": ["two"],
        "changed": ["one"],
    }
    assert result["changed_at"] is not None


def test_unchanged_catalog_preserves_last_change_summary(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    catalog.refresh_hackerone_catalog(
        store,
        client=FakeClient([_resource("one", "One")]),
    )
    changed = catalog.refresh_hackerone_catalog(
        store,
        client=FakeClient(
            [
                _resource("one", "One"),
                _resource("two", "Two"),
            ]
        ),
    )
    stable = catalog.refresh_hackerone_catalog(
        store,
        client=FakeClient(
            [
                _resource("one", "One"),
                _resource("two", "Two"),
            ]
        ),
    )

    assert stable["fingerprint"] == changed["fingerprint"]
    assert stable["change_sequence"] == changed["change_sequence"] == 1
    assert stable["changes"] == changed["changes"] == {
        "added": ["two"],
        "removed": [],
        "changed": [],
    }
    assert stable["changed_at"] == changed["changed_at"]


def test_catalog_poll_interval_validation(monkeypatch):
    monkeypatch.setenv("XBOW_HACKERONE_CATALOG_POLL_SECONDS", "299")
    try:
        catalog.catalog_poll_seconds()
    except ValueError as exc:
        assert "between 300 and 86400" in str(exc)
    else:
        raise AssertionError("expected invalid interval to fail closed")
