# Vault migration

This runbook moves legacy server-side secret sources into xbow-perso's encrypted AES-256-GCM vault without exposing secret values in command output.

## Supported legacy sources

The migration utility recognizes:

- `XBOW_API_TOKEN` or `XBOW_API_TOKEN_FILE` → `api_token`
- `XBOW_HACKERONE_API_USERNAME` → `hackerone_api_username`
- `XBOW_HACKERONE_API_TOKEN` → `hackerone_api_token`
- `XBOW_PENTAGI_API_TOKEN` → `pentagi_api_token`
- `LLM_API_KEY` → `llm_api_key`
- `PERPLEXITY_API_KEY` → `perplexity_api_key`
- `XBOW_AUDIT_HMAC_KEY` → `audit_hmac_key`
- `XBOW_TOTP_SECRET` → `totp_secret`
- `XBOW_ALERT_WEBHOOK_HMAC_KEY` → `alert_webhook_hmac_key`
- every `XBOW_BROWSER_SECRET_<NAME>` → `browser.<name-lowercase>`

Database/Redis passwords are intentionally not migrated into this application vault because Compose itself needs them before the application starts.

## Master key

Production migration requires a file-backed vault master key:

```bash
XBOW_VAULT_MASTER_KEY_FILE=/run/secrets/xbow_vault_master_key
```

The migration rejects inline `XBOW_VAULT_MASTER_KEY`.

If the configured master-key file does not yet exist, `apply` creates a random 32-byte URL-safe base64 key with mode `0600`. The key value is never printed.

## 1. Plan

Keep `XBOW_VAULT_ENABLED=false` while legacy sources still exist.

```bash
PYTHONPATH=backend python -m app.vault_migration plan
```

The plan prints only secret names, source variable names and migration state. Secret values are never returned.

A conflicting existing vault entry blocks migration instead of overwriting it.

## 2. Apply

```bash
PYTHONPATH=backend python -m app.vault_migration apply
```

Each value is written to the vault and read back for verification. The result lists only migrated vault names and the legacy source names that can be removed.

Applying does **not** enable vault mode automatically. This avoids putting the running application into a state where legacy variables and vault mode conflict.

## 3. Rewrite the server .env

After `apply` succeeds:

```bash
PYTHONPATH=backend python -m app.vault_migration rewrite-env --env-file .env
```

Before deleting any assignment, the command verifies that its current in-process legacy value exactly matches the encrypted vault entry.

It then:

- creates `.env.pre-vault.bak` with mode `0600`;
- removes migrated legacy secret assignments;
- removes any inline vault master-key assignment;
- sets `XBOW_VAULT_ENABLED=true`;
- sets `XBOW_VAULT_MASTER_KEY_FILE` to the configured key-file path;
- preserves unrelated configuration such as `DRY_RUN` and active-scan switches.

The backup is intentionally not overwritten. A second rewrite therefore fails closed until the operator deliberately archives or removes the first backup.

## 4. Restart and verify

Restart backend/workers with the same safe execution settings and verify:

- control API authentication still works;
- HackerOne read-only connection still returns success;
- `/ready` is healthy;
- deployment preflight reports the vault enabled with a file-backed key;
- no legacy secret variables remain in the service configuration.

Do not enable scanning or HackerOne submission as part of the secret migration.
