from __future__ import annotations

from app import github_learning_sync as learning


class FakeStore:
    def __init__(self):
        self.batch = {
            "id": "batch-123",
            "mode": "parallel",
            "state": "completed",
            "created_at": "2026-09-21T12:00:00+00:00",
            "updated_at": "2026-09-21T12:30:00+00:00",
            "summary": {"done": 1, "blocked": 0},
            "members": [
                {
                    "handle": "example-program",
                    "status": "done",
                    "campaign_id": "campaign-123",
                }
            ],
        }
        self.campaign = {
            "id": "campaign-123",
            "state": "completed",
            "created_at": "2026-09-21T12:00:00+00:00",
            "updated_at": "2026-09-21T12:25:00+00:00",
            "findings": [
                {
                    "title": "Sensitive-looking title",
                    "severity": "high",
                    "status": "confirmed",
                    "cwe": "CWE-200",
                    "discovered_by": "scanner",
                    "validated_by": "reviewer",
                    "evidence": ["RAW SECRET EVIDENCE"],
                    "reproduction_steps": ["do not export this payload"],
                }
            ],
            "events": [
                {"type": "campaign_created"},
                {"type": "recon_task_completed"},
                {"type": "worker_outcome"},
            ],
        }
        self.version = 1

    def get_campaign(self, campaign_id):
        return self.campaign if campaign_id == "campaign-123" else None

    def list_hackerone_batches(self, *, limit):
        return [dict(self.batch)]

    def get_hackerone_batch_record(self, batch_id):
        if batch_id != "batch-123":
            return None
        return dict(self.batch), self.version

    def save_hackerone_batch(self, document, *, expected_version=None):
        assert expected_version == self.version
        self.batch = dict(document)
        self.version += 1
        return self.version


def test_learning_digest_is_detailed_but_excludes_raw_evidence_and_payloads():
    store = FakeStore()
    digest = learning.build_learning_digest(store, store.batch)
    encoded = str(digest)

    campaign = digest["members"][0]["campaign"]
    assert campaign["finding_count"] == 1
    assert campaign["confirmed_findings"] == 1
    assert campaign["severities"] == {"high": 1}
    assert campaign["event_types"]["recon_task_completed"] == 1
    assert "RAW SECRET EVIDENCE" not in encoded
    assert "do not export this payload" not in encoded
    assert "evidence" not in campaign["finding_brief"][0]
    assert "reproduction_steps" not in campaign["finding_brief"][0]


def test_learning_sync_creates_idempotent_github_issue(monkeypatch):
    store = FakeStore()
    calls = []

    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_ENABLE_GITHUB_LEARNING_SYNC", "true")
    monkeypatch.setenv("XBOW_GITHUB_LEARNING_REPO", "dbrckk/xbow-perso")
    monkeypatch.setenv("XBOW_GITHUB_LEARNING_TOKEN", "test-token-value")

    def fake_github(method, url, token, payload=None):
        calls.append((method, url, payload))
        if "search/issues" in url:
            return {"items": []}
        return {"number": 42, "html_url": "https://github.example/issues/42"}

    monkeypatch.setattr(learning, "_github_json", fake_github)
    result = learning.sync_batch_learning_issue(store, store.batch)

    assert result["status"] == "synced"
    assert result["issue_number"] == 42
    assert any(method == "POST" for method, _url, _payload in calls)
    post = next(payload for method, _url, payload in calls if method == "POST")
    assert "RAW SECRET EVIDENCE" not in post["body"]
    assert "do not export this payload" not in post["body"]


def test_completed_batch_sync_is_persisted_for_journal(monkeypatch):
    store = FakeStore()

    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_ENABLE_GITHUB_LEARNING_SYNC", "true")
    monkeypatch.setenv("XBOW_GITHUB_LEARNING_REPO", "dbrckk/xbow-perso")
    monkeypatch.setenv("XBOW_GITHUB_LEARNING_TOKEN", "test-token-value")
    monkeypatch.setattr(
        learning,
        "sync_batch_learning_issue",
        lambda _store, _batch: {
            "status": "synced",
            "repository": "dbrckk/xbow-perso",
            "issue_number": 7,
            "issue_url": "https://github.example/issues/7",
            "synced_at": "2026-09-21T12:31:00+00:00",
        },
    )

    assert learning.sync_completed_learning_batches(store, limit=20) == 1
    assert store.batch["learning_repo_sync"]["status"] == "synced"
    assert store.batch["learning_repo_sync"]["issue_number"] == 7
