from app.hackerone_intelligence import (
    build_hackerone_intelligence,
    classify_report,
    fetch_disclosed_hacktivity,
    normalize_hacktivity_item,
    refresh_hackerone_intelligence,
)
from app.storage import Storage


def _item(
    report_id: str,
    *,
    title: str,
    cwe: str,
    severity: str,
    award: float,
    handle: str,
    currency: str = "usd",
    disclosed: bool = True,
    summary: str = "",
    disclosed_at: str = "2026-09-01T12:00:00Z",
):
    return {
        "id": report_id,
        "type": "report",
        "attributes": {
            "title": title,
            "substate": "Resolved",
            "url": f"https://hackerone.com/reports/{report_id}",
            "disclosed_at": disclosed_at,
            "submitted_at": "2026-08-01T12:00:00Z",
            "cve_ids": [],
            "cwe": cwe,
            "severity_rating": severity,
            "votes": 12,
            "total_awarded_amount": award,
            "disclosed": disclosed,
        },
        "relationships": {
            "report_generated_content": {
                "data": {
                    "type": "report_generated_content",
                    "attributes": {"hacktivity_summary": summary},
                }
            },
            "program": {
                "data": {
                    "type": "program",
                    "attributes": {
                        "handle": handle,
                        "name": handle.title(),
                        "currency": currency,
                        "url": f"https://hackerone.com/{handle}",
                    },
                }
            },
        },
    }


class FakeClient:
    def __init__(self, high_value, recent):
        self.high_value = high_value
        self.recent = recent
        self.calls = []

    def get_all_pages(self, path, query=None, *, max_pages=100, page_size=100):
        self.calls.append(
            {
                "path": path,
                "query": dict(query or {}),
                "max_pages": max_pages,
                "page_size": page_size,
            }
        )
        if query.get("sort") == "-total_awarded_amount":
            return list(self.high_value)
        if query.get("sort") == "-disclosed_at":
            return list(self.recent)
        raise AssertionError(query)


def test_normalize_disclosed_hacktivity_is_redacted_and_bounded():
    raw = _item(
        "123",
        title="GraphQL access control leak",
        cwe="Improper Access Control",
        severity="critical",
        award=20000,
        handle="acme",
        summary="Confidential object fields were visible through GraphQL.",
    )

    item = normalize_hacktivity_item(raw)

    assert item is not None
    assert item["id"] == "123"
    assert item["program_handle"] == "acme"
    assert item["currency"] == "USD"
    assert item["award_amount"] == 20000
    assert "relationships" not in item
    assert "reporter" not in item
    assert classify_report(item) == "access_control"


def test_undisclosed_hacktivity_is_not_learned():
    raw = _item(
        "124",
        title="redacted",
        cwe="",
        severity="high",
        award=5000,
        handle="acme",
        disclosed=False,
    )

    assert normalize_hacktivity_item(raw) is None


def test_fetch_combines_high_value_and_recent_views(monkeypatch):
    monkeypatch.setenv("XBOW_HACKERONE_INTEL_MAX_PAGES", "1")
    shared = _item(
        "1",
        title="IDOR",
        cwe="Improper Access Control",
        severity="critical",
        award=10000,
        handle="one",
    )
    client = FakeClient(
        [shared],
        [
            shared,
            _item(
                "2",
                title="Race condition in redemption",
                cwe="Race Condition",
                severity="high",
                award=6000,
                handle="two",
            ),
        ],
    )

    reports = fetch_disclosed_hacktivity(client=client)

    assert {item["id"] for item in reports} == {"1", "2"}
    assert len(client.calls) == 2
    assert all(call["path"] == "hackers/hacktivity" for call in client.calls)
    assert all(call["query"]["queryString"] == "disclosed:true" for call in client.calls)
    assert all(call["max_pages"] == 1 for call in client.calls)


def test_intelligence_prioritizes_patterns_and_historical_value():
    reports = [
        normalize_hacktivity_item(
            _item(
                "1",
                title="IDOR exposed another account",
                cwe="Improper Access Control",
                severity="critical",
                award=20000,
                handle="one",
            )
        ),
        normalize_hacktivity_item(
            _item(
                "2",
                title="Authorization bypass in GraphQL",
                cwe="Privilege Escalation",
                severity="high",
                award=12000,
                handle="one",
            )
        ),
        normalize_hacktivity_item(
            _item(
                "3",
                title="Race condition allowed repeated redemption",
                cwe="Race Condition",
                severity="high",
                award=6000,
                handle="two",
            )
        ),
    ]
    reports = [item for item in reports if item is not None]

    state = build_hackerone_intelligence(reports)

    assert state["source"] == "public_disclosed_hacktivity"
    assert state["automatic_tool_enablement"] is False
    assert state["contains_secrets"] is False
    assert state["categories"][0]["category"] == "access_control"
    assert state["program_signals"]["one"]["usd_awarded_max"] == 20000
    assert state["program_signals"]["one"]["historical_only"] is True
    access_gap = next(
        item for item in state["capability_gaps"]
        if item["category"] == "access_control"
    )
    assert access_gap["capability"] == "authorization-differential"
    assert access_gap["status"] == "missing"
    assert access_gap["automatic_execution"] is False


def test_refresh_persists_hacktivity_learning(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_HACKERONE_INTEL_MAX_PAGES", "1")
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    client = FakeClient(
        [
            _item(
                "1",
                title="MFA bypass and account takeover",
                cwe="Authentication Bypass",
                severity="critical",
                award=15000,
                handle="authco",
            )
        ],
        [],
    )

    state = refresh_hackerone_intelligence(store, client=client)

    persisted = store.get_hackerone_intelligence_state()
    assert persisted is not None
    assert persisted["report_count"] == 1
    assert persisted["reports"][0]["program_handle"] == "authco"
    assert persisted["contains_secrets"] is False
    assert state["checked_at"] == persisted["checked_at"]
