# Signed inert session lifecycle for Strix

The runner provides an **in-memory, non-executable session preparation**
facility over its internal-only authenticated RPC transport. This is a
separate API from the four upstream-compatible session lifecycle endpoints,
which remain **disabled**.

## Internal protocol

All mutation and recovery endpoints require `POST`, `Content-Type: application/json`, and
`strix-runner-rpc-v1` HMAC headers with a fresh timestamp and 128-bit
nonce. The request body is covered by the RPC signature.

| Endpoint | Success | Requirements |
| --- | --- | --- |
| `/v1/session/prepare` | 201 `prepared` | Signed v2 ticket bound to request id, image, exposed ports, manifest digest and validity window |
| `/v1/session/release` | 200 `released` | Existing random prepared session id and matching contract hash, signed with runner RPC key |
| `/v1/session/plan-receipt` | 200 `plan_verified` | Session-bound HMAC request carrying the exact canonical metadata JSON; SHA-256 and signed counters must match |
| `/v1/session/file-chunk` | 200 `chunk_received` / `file_verified` | Ordered, HMAC-authenticated Base64 bytes bound to a verified plan entry, its SHA-256, contract, session and offset |
| `/v1/session/preparation-status` | 200 `prepared` or 404 | Read-only recovery of a live prepared session by original request ID, contract hash and manifest digest; no TTL refresh or new ticket |
| `/v1/session/verification-status` | 200 `verification_status` | Authenticated read-only status for an active session: signed-plan acceptance, per-file received byte count, incremental SHA-256 prefix, finalized/failed flags and total verified count; no content bytes |
| `/v1/session/release-status` | 200 `released` or 404 | Read-only lookup of the **specific release request identity** and matching session/contract/manifest in a bounded ephemeral cache; does not create or release a session |

A preparation records **only** the random session id, signed execution-contract
hash, original preparation request ID, manifest digest, signed plan entry/byte counts, one-shot verification flag, and monotonic expiry. It does **not** retain manifests,
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
`inert_preparation_operations: ["prepare", "release", "plan-receipt", "file-chunk", "preparation-status", "verification-status", "release-status"]` while
`implemented_operations: []` continues to mean **no executable upstream
lifecycle operations are implemented**.

## Verification

The existing CI checks sign an admission ticket and runner RPC envelope
using ephemeral CI fixtures, exercise prepare/replay rejection/invalid digest/
wrong-contract release/valid release/duplicate release across the *real
broker-to-runner Docker network*, and confirm legacy `/v1/session/create`
remains blocked even with a correctly signed ticket.

### Security limitations before active execution

This API is deliberately an intermediate integration step. The plan receipt
verifies **canonical manifest-plan metadata** received in memory (at most
256 KiB) against the signed digest and counts, and rejects duplicate
receipts, unsafe paths and noncanonical JSON. After this proof, the separate
file-chunk operation can accept **actual inline-file bytes** (not local
directories) in strictly ordered chunks of at most 64 KiB each. Each RPC is
signed with a fresh nonce, and the complete file SHA-256 must equal the
content address in the previously verified manifest plan. A file is
accepted only after its full declared byte count and a final digest check.
Wrong offsets cannot advance its state; a final digest mismatch permanently
poisons that file receipt for the session. Empty files require a final empty
chunk. A session holds only path/digest/length metadata and incremental hash
states (at most 128 entries and 4 MiB aggregate declared bytes), **never
the transferred file data**.

The payload's Base64 representation must be canonical; malformed Base64,
out-of-order bytes, incorrect lengths and contradictory final flags are
rejected without creating a file. Zero local-directory data is accepted.
No disk file materialization, process execution or target traffic is
implemented. Successfully checking all file digests does not enable a runnable
Strix session. The v2 ticket format includes signed expiration,
and the private journal prevents reuse of an unexpired ticket after runner
restart. Deleting or rolling back the Docker volume erases that history;
volume retention and backup policy matter. Do **not** enable active scan
dispatch. Future work must separately design secure handling of local-directory sources,
persistent session ownership if needed, and isolated materialization and
egress policy enforcement before any scanner process runs.

## Trusted broker orchestration (no public upload route)

The broker module `app.strix_broker_inert_transfer` exposes
`verify_inert_manifest_files(contract=..., image=..., exposed_ports=..., files=...)`
for **internal trusted code only**; it deliberately adds no HTTP upload
endpoint and does not start a scan. The broker verifies the signed execution
contract and primary-target scope before sending anything to the runner.
Only a mapping of workspace-relative paths to **in-memory immutable bytes** is
accepted. Local directory sources, environment values, host paths and bind
mounts are not accepted. The manifest admission module independently validates
path overlap, UTF-8, per-file 1 MiB, total 4 MiB and 128-entry bounds before
the broker signs a fresh 120-second preparation ticket.

After preparation the broker sends canonical plan JSON and all inline files as
64 KiB signed RPC chunks over its fixed `http://strix-runner:8092` internal
endpoint. Proxies and redirects are disabled. Every runner receipt is checked
for expected session, offsets, progress counts and explicit no-execution flags.
The broker **always attempts a signed session release** after a successfully
acknowledged preparation, including when a later chunk or network request
fails. Only a verified release permits a success receipt, which contains
counts and digests, not file bytes.

The broker **never retransmits a preparation ticket** after an ambiguous
network failure. Instead it makes **one** authenticated, read-only
`/v1/session/preparation-status` request bound to the original preparation
request ID, signed contract hash and manifest digest. The runner returns the
session ID only while it is live, without creating a new ticket, modifying its
replay journal, or extending the monotonic 900-second expiry.

If preparation never arrived, the lookup returns 404 and the broker fails
without replaying the ticket. If both requests fail, the runner's original
900-second TTL cleans any orphaned **inert** state. Ambiguous plan and file-chunk responses are reconciled by at most one
authenticated, **read-only** verification status request. A lost plan reply
may be accepted only if the expected signed plan is verified; a chunk reply
may be accepted only when the exact byte count **and SHA-256 of the complete
accepted prefix** match what the broker sent, with no failed file state.
This makes coincidentally correct offsets insufficient for recovery. No
mutation is retried, no file content is exposed by status, and an absent,
failed or conflicting proof aborts the transfer.

For an ambiguous release response, the broker queries a bounded,
process-local release receipt by the **exact original release request ID**,
session ID, contract hash and manifest digest. A missing session or a
natural TTL expiry is **not** evidence that an explicit release succeeded.
Release receipts expire at the original session TTL, require the runner's
existing HMAC transport authentication, and never retain file contents.
An unproven release cannot produce a success result. A process restart can
erase this intentionally ephemeral evidence; the caller must then fail
closed. No code enables additional scanning or target traffic.
Neither case enables file materialization, a runnable Strix session or
target egress. The runner RPC signing key is available only to the
trusted broker and runner, never scanner workloads.

CI invokes the trusted broker helper *inside the real broker container* over
the isolated Compose network, checking valid multi-file and empty-file
content, scope/signature rejection, oversized/unsafe paths and release after
a deliberately injected mid-stream transport interruption.

CI verifies a 4 MiB aggregate multi-file transfer and rejects even one byte
above the quota. It proves recovery after a lost successful preparation
response, no ticket replay when preparation never arrived, and an in-process
monotonic-time check showing 1 second remaining after 899 seconds and a
404 after 900 seconds. No executable Strix operation is introduced.

The Compose integration proof also exercises a successfully applied
plan/chunk/release with a lost response, an unreceived chunk, a corrupted
same-length content prefix, a release that never reached the runner, and
**exactly 128 empty inline files** versus 129 (rejected). The runner returns
SHA-256 digests and counters only, never received file bytes or materialized
paths. Ambiguous results are not replayed.
