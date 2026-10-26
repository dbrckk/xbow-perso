# Signed inert session lifecycle for Strix

The runner provides an **in-memory, non-executable session preparation**
facility over its internal-only authenticated RPC transport. This is a
separate API from the four upstream-compatible session lifecycle endpoints,
which remain **disabled**.

## Internal protocol

Both endpoints require `POST`, `Content-Type: application/json`, and
`strix-runner-rpc-v1` HMAC headers with a fresh timestamp and 128-bit
nonce. The request body is covered by the RPC signature.

| Endpoint | Success | Requirements |
| --- | --- | --- |
| `/v1/session/prepare` | 201 `prepared` | Signed v2 ticket bound to request id, image, exposed ports, manifest digest and validity window |
| `/v1/session/release` | 200 `released` | Existing random prepared session id and matching contract hash, signed with runner RPC key |

A preparation records **only** the random session id, signed execution-contract
hash, manifest digest, and monotonic expiry. It does **not** retain manifests,
copy files, mount local paths, open ports, create containers, spawn processes,
or send traffic to a target. It is not a runnable Strix session.

Preparation admission:
- Maximum 128 simultaneous preparations.
- Each record automatically expires after 900 seconds.
- Signed tickets expire after 120 seconds, with only 5 seconds of future-clock
  tolerance; altered or expired claims are rejected.
- Maximum 1,024 recent preparation ticket identities (bounded and pruned
  after expiration); the same `(contract_hash, request_id)` is rejected on
  retry even after a session is released within its retention interval.
- Prepared sessions remain process-local and disappear on restart.
  Consumed ticket identities persist transactionally in a private SQLite
  journal on the dedicated `strix-runner-replay` named Docker volume.
  New preparations fail closed if the journal is unavailable or invalid.
  The journal stores only contract hashes, request IDs and expirations;
  it never contains manifest bytes, host paths or credentials.
- The journal is bounded to 1,024 live ticket identities, removes expired
  records and uses synchronous SQLite transactions with a 4 MiB page cap.
- Released or expired sessions cannot be released again.
- Different contract hashes cannot release another contract's session.
- `active_execution=True` rejects inert prepare/release operations.

The root filesystem stays read-only, the process stays non-root, and no
host bind mounts, Docker socket, exposed host ports or external networks
are introduced. A single named volume contains only replay metadata.

The runner readiness response advertises
`inert_preparation_operations: ["prepare", "release"]` while
`implemented_operations: []` continues to mean **no executable upstream
lifecycle operations are implemented**.

## Verification

The existing CI checks sign an admission ticket and runner RPC envelope
using ephemeral CI fixtures, exercise prepare/replay rejection/invalid digest/
wrong-contract release/valid release/duplicate release across the *real
broker-to-runner Docker network*, and confirm legacy `/v1/session/create`
remains blocked even with a correctly signed ticket.

### Security limitations before active execution

This API is deliberately an intermediate integration step. The signed
manifest admission ticket describes digests and metadata but does not prove
the actual uploaded bytes were received or verified; no upload or
materialization is implemented. The v2 ticket format includes signed expiration,
and the private journal prevents reuse of an unexpired ticket after runner
restart. Deleting or rolling back the Docker volume erases that history;
volume retention and backup policy matter. Do **not** enable active scan
dispatch. Future work must add content-addressed upload with byte verification;
persistent session ownership
if needed; and egress policy enforcement before any scanner process runs.

## Bounded byte-integrity primitive (not an upload)

The runner module includes `verify_inert_content_digest` to validate a
strict Base64-encoded, at-most-64-KiB in-memory byte sample against an
expected lowercase SHA-256 digest using constant-time digest comparison.
Malformed encoding, excessive length and digest mismatches fail closed.
The helper returns only the verified byte length and does not persist the
bytes, open files, register an RPC endpoint, materialize a manifest or run
any scanner. A full manifest transfer still requires a separately reviewed
content-addressed protocol and an isolated integration proof.
