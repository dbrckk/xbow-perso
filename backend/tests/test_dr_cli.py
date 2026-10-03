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
