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
from .queue_backend import create_queue
from .queue_recovery import build_queue_recovery_assessment
from .recovery_attestation import (
    RecoveryAttestationError,
    build_recovery_attestation,
    collect_recovery_campaign_audits,
    load_and_verify_recovery_attestation,
    write_recovery_attestation,
)
from .storage_backend import create_storage


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

    attest = sub.add_parser("attest")
    attest.add_argument("--manifest", required=True)
    attest.add_argument("--postgres-dump", required=True)
    attest.add_argument("--redis-snapshot", required=True)
    attest.add_argument("--vault-copy", required=True)
    attest.add_argument("--output", required=True)

    verify_attestation = sub.add_parser("verify-attestation")
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
        elif args.command == "attest":
            output_path = Path(args.output).resolve(strict=False)
            protected_paths = {
                Path(args.manifest).resolve(strict=False),
                Path(args.postgres_dump).resolve(strict=False),
                Path(args.redis_snapshot).resolve(strict=False),
                Path(args.vault_copy).resolve(strict=False),
            }
            if output_path in protected_paths:
                raise RecoveryAttestationError(
                    "attestation output must not overwrite recovery inputs"
                )
            backup_verification = verify_backup_manifest(
                args.manifest,
                postgres_dump=args.postgres_dump,
                redis_snapshot=args.redis_snapshot,
                vault_copy=args.vault_copy,
            )
            queue_assessment = build_queue_recovery_assessment(create_queue())
            campaign_audits = collect_recovery_campaign_audits(create_storage())
            attestation = build_recovery_attestation(
                backup_verification=backup_verification,
                queue_assessment=queue_assessment,
                campaign_audits=campaign_audits,
            )
            write_recovery_attestation(attestation, args.output)
            result = {
                "ok": attestation["ready_to_restore"],
                "decision": attestation["decision"],
                "attestation": args.output,
                "attestation_digest": attestation["attestation_digest"],
                "contains_targets": False,
                "contains_payloads": False,
                "contains_secrets": False,
            }
            if not attestation["ready_to_restore"]:
                print(json.dumps(result, sort_keys=True))
                return 1
        else:
            verification = load_and_verify_recovery_attestation(args.attestation)
            result = {"ok": verification["valid"], **verification}
            if not verification["valid"]:
                print(json.dumps(result, sort_keys=True))
                return 1
    except (DisasterRecoveryError, RecoveryAttestationError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
