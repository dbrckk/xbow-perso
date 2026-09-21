from pathlib import Path

from app.runtime_learning import learning_delivery_status, persist_learning_brief


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_learning_outbox_is_local_and_private_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_REPO_LEARNING_OUTBOX", str(tmp_path / "learning"))
    monkeypatch.setenv("XBOW_ENABLE_REPO_LEARNING_PUSH", "false")

    status = persist_learning_brief(
        {
            "batch_id": "batch-123",
            "kind": "xbow_runtime_learning_brief",
            "contains_secrets": False,
        }
    )

    assert status["queued"] is True
    assert status["delivered"] is False
    assert status["reason"] == "github_delivery_disabled"

    current = learning_delivery_status("batch-123")
    assert current["queued"] is True
    assert current["delivered"] is False

    path = tmp_path / "learning" / "batch-123.json"
    assert path.is_file()
    assert path.stat().st_mode & 0o077 == 0


def test_runtime_learning_workflow_accepts_only_owner_authored_learning_issues():
    workflow = (ROOT / ".github" / "workflows" / "runtime-learning-ingest.yml").read_text(
        encoding="utf-8"
    )

    assert "github.event.issue.user.login == github.repository_owner" in workflow
    assert "startsWith(github.event.issue.title, '[runtime-learning]')" in workflow
    assert ".ai/runtime-learning" in workflow
    assert "reusable-semantic.yml@main" in workflow
