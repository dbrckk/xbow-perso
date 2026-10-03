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



def test_attest_cli_refuses_recovery_input_collision(monkeypatch, tmp_path, capsys):
    postgres = tmp_path / "postgres.dump"
    redis = tmp_path / "dump.rdb"
    vault = tmp_path / "secrets.vault.json"
    manifest = tmp_path / "manifest.json"
    for path in (postgres, redis, vault, manifest):
        path.write_bytes(b"fixture")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dr_cli",
            "attest",
            "--manifest",
            str(manifest),
            "--postgres-dump",
            str(postgres),
            "--redis-snapshot",
            str(redis),
            "--vault-copy",
            str(vault),
            "--output",
            str(manifest),
        ],
    )

    assert dr_cli.main() == 1
    output = capsys.readouterr().out
    assert "must not overwrite recovery inputs" in output
    assert manifest.read_bytes() == b"fixture"



def test_queue_check_cli_is_read_only_and_redacted(monkeypatch, capsys):
    class Backend:
        pass

    monkeypatch.setattr(sys, "argv", ["dr_cli", "queue-check"])
    monkeypatch.setattr(dr_cli, "create_queue", lambda: Backend())
    monkeypatch.setattr(
        dr_cli,
        "build_queue_recovery_assessment",
        lambda _backend: {
            "safe_to_resume": True,
            "jobs_total": 1,
            "jobs_assessed": 1,
            "issues_total": 0,
            "issues_by_severity": {"critical": 0, "warning": 0},
            "issues": [],
            "read_only": True,
            "automatic_requeue": False,
            "automatic_job_creation": False,
            "automatic_mutation": False,
            "payloads_exposed": False,
            "worker_identities_exposed": False,
        },
    )

    assert dr_cli.main() == 0
    output = capsys.readouterr().out
    assert '"read_only": true' in output
    assert '"automatic_mutation": false' in output
