from __future__ import annotations

import argparse
import json
from pathlib import Path

from .queue_backend import create_queue
from .recovery_attestation import (
    RecoveryAttestationError,
    build_recovery_attestation,
    collect_recovery_campaign_audits,
    load_and_verify_recovery_attestation,
    write_recovery_attestation,
)
from .storage import Storage
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

    sub.add_parser(
        "queue-check",
        help="Read-only post-restore queue consistency and lease assessment.",
    )

    attest = sub.add_parser(
        "attest",
        help="Create a signed recovery attestation after all recovery checks pass.",
    )
    attest.add_argument("--manifest", required=True)
    attest.add_argument("--postgres-dump", required=True)
    attest.add_argument("--redis-snapshot", required=True)
    attest.add_argument("--vault-copy", required=True)
    attest.add_argument("--output", required=True)

    verify_attestation = sub.add_parser(
        "verify-attestation",
        help="Verify a signed recovery attestation.",
    )
    verify_attestation.add_argument("--attestation", required=True)

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
        elif args.command == "verify":
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
        elif args.command == "queue-check":
            assessment = create_queue().recovery_assessment()
            result = {"ok": bool(assessment["safe_to_resume"]), **assessment}
            if not result["ok"]:
                print(json.dumps(result, sort_keys=True))
                return 1
        elif args.command == "attest":
            verification = verify_backup_manifest(
                args.manifest,
                postgres_dump=args.postgres_dump,
                redis_snapshot=args.redis_snapshot,
                vault_copy=args.vault_copy,
            )
            queue_backend = create_queue()
            assessment = queue_backend.recovery_assessment()
            audits = collect_recovery_campaign_audits(
                Storage(),
                queue_backend,
            )
            attestation = build_recovery_attestation(
                backup_verification=verification,
                queue_assessment=assessment,
                campaign_audits=audits,
            )
            write_recovery_attestation(attestation, args.output)
            result = {
                "ok": True,
                "attestation": args.output,
                "attestation_digest": attestation["attestation_digest"],
                "campaigns_checked": attestation["campaign_audits"]["campaigns_checked"],
            }
        else:
            verification = load_and_verify_recovery_attestation(args.attestation)
            result = {"ok": bool(verification["valid"]), **verification}
            if not result["ok"]:
                print(json.dumps(result, sort_keys=True))
                return 1
    except (DisasterRecoveryError, RecoveryAttestationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
