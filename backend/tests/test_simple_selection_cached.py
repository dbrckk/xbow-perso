from app import hackerone_api


class _Store:
    def get_hackerone_catalog_state(self):
        return {
            "checked_at": "2026-09-22T00:00:00+00:00",
            "changes": {"added": [], "removed": [], "changed": []},
            "programs": [
                {
                    "handle": chr(97 + index),
                    "name": f"Program {index}",
                    "submission_state": "open",
                    "state": "public_mode",
                    "offers_bounties": True,
                    "gold_standard_safe_harbor": True,
                }
                for index in range(8)
            ],
        }

    def get_hackerone_intelligence_state(self):
        return {
            "program_signals": {
                chr(97 + index): {
                    "historical_value_score": 10 + index,
                    "usd_awarded_max": 1000 * (index + 1),
                }
                for index in range(8)
            }
        }

    def list_hackerone_review_profiles(self, *, limit):
        assert limit == 1000
        return [
            {"handle": chr(97 + index), "snapshot_sha256": f"old-{index}"}
            for index in range(8)
        ]

    def list_campaigns(self, *, limit):
        assert limit == 1000
        return []


def test_simple_selection_uses_local_catalog_without_live_hackerone(monkeypatch):
    import app.main as main

    store = _Store()
    monkeypatch.setattr(main, "storage", lambda: store)

    def should_not_refresh(*args, **kwargs):
        raise AssertionError("live HackerOne catalog refresh must not run when cache exists")

    monkeypatch.setattr(hackerone_api, "refresh_hackerone_catalog", should_not_refresh)
    result = hackerone_api.hackerone_simple_selection()

    assert result["catalog_source"] == "local-cache"
    assert result["selection_requires_live_hackerone"] is False
    assert result["selection_count"] == 6
    assert result["review_count"] == 0
    assert result["revalidation_count"] == 6
    assert result["launch_ready"] is True
