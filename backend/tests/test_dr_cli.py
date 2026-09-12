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
