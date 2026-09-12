from __future__ import annotations

import argparse
import json

from .secret_vault import SecretVaultError, rekey_vault


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.vault_cli",
        description="Local encrypted-vault maintenance commands.",
    )
    parser.add_argument("command", choices=("rekey",))
    args = parser.parse_args()

    try:
        if args.command == "rekey":
            result = rekey_vault()
        else:
            raise SecretVaultError("unsupported vault command")
    except SecretVaultError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
