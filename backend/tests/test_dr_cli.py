import sys

from app import dr_cli


def test_manifest_cli_refuses_output_collision(monkeypatch, tmp_path, capsys):
    postgres = tmp_path / "postgres.dump"
    redis = tmp_path / "dump.rdb"
    vault = tmp_path / "secrets.vault.json"
    postgres.write_bytes(b"postgres")
    redis.write_bytes(b"redis")
    vault.write_bytes(b"vault")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dr_cli",
            "manifest",
            "--postgres-dump",
            str(postgres),
            "--redis-snapshot",
            str(redis),
            "--vault-copy",
            str(vault),
            "--output",
            str(postgres),
        ],
    )

    assert dr_cli.main() == 1
    output = capsys.readouterr().out
    assert "must not overwrite a backup artifact" in output
    assert postgres.read_bytes() == b"postgres"



def test_queue_check_cli_is_read_only_and_returns_success_when_safe(monkeypatch, capsys):
    class Queue:
        def recovery_assessment(self):
            return {
                "safe_to_resume": True,
                "issues_total": 0,
                "automatic_requeue": False,
                "automatic_job_creation": False,
                "automatic_mutation": False,
            }

    monkeypatch.setattr(dr_cli, "create_queue", lambda: Queue())
    monkeypatch.setattr(sys, "argv", ["dr_cli", "queue-check"])

    assert dr_cli.main() == 0
    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"automatic_requeue": false' in output


def test_queue_check_cli_fails_closed_when_reconciliation_is_required(monkeypatch, capsys):
    class Queue:
        def recovery_assessment(self):
            return {
                "safe_to_resume": False,
                "issues_total": 1,
                "issues": [
                    {
                        "job_id": "job-1",
                        "code": "expired_running_lease",
                        "severity": "warning",
                        "recommended_action": "review_lease_recovery",
                    }
                ],
                "automatic_requeue": False,
                "automatic_job_creation": False,
                "automatic_mutation": False,
            }

    monkeypatch.setattr(dr_cli, "create_queue", lambda: Queue())
    monkeypatch.setattr(sys, "argv", ["dr_cli", "queue-check"])

    assert dr_cli.main() == 1
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert "expired_running_lease" in output
