from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dr_manifest import (
    DisasterRecoveryError,
    build_backup_manifest,
    verify_backup_manifest,
    write_backup_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.dr_cli",
        description="Non-destructive disaster-recovery backup integrity tools.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("manifest")
    create.add_argument("--postgres-dump", required=True)
    create.add_argument("--redis-snapshot", required=True)
    create.add_argument("--vault-copy", required=True)
    create.add_argument("--output", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--postgres-dump", required=True)
    verify.add_argument("--redis-snapshot", required=True)
    verify.add_argument("--vault-copy", required=True)

    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "manifest":
            output_path = Path(args.output).resolve(strict=False)
            backup_paths = {
                Path(args.postgres_dump).resolve(strict=False),
                Path(args.redis_snapshot).resolve(strict=False),
                Path(args.vault_copy).resolve(strict=False),
            }
            if output_path in backup_paths:
                raise DisasterRecoveryError(
                    "manifest output must not overwrite a backup artifact"
                )
            manifest = build_backup_manifest(
                postgres_dump=args.postgres_dump,
                redis_snapshot=args.redis_snapshot,
                vault_copy=args.vault_copy,
            )
            write_backup_manifest(manifest, args.output)
            result = {
                "ok": True,
                "manifest": args.output,
                "artifacts": len(manifest["artifacts"]),
            }
        else:
            verification = verify_backup_manifest(
                args.manifest,
                postgres_dump=args.postgres_dump,
                redis_snapshot=args.redis_snapshot,
                vault_copy=args.vault_copy,
            )
            result = {"ok": verification["valid"], **verification}
            if not verification["valid"]:
                print(json.dumps(result, sort_keys=True))
                return 1
    except DisasterRecoveryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
