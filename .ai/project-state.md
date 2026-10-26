# Project state

Status: active

## Working
- Central AI repo-map generation is configured through dbrckk/repo-standards.
- Repository agent instructions are present.
- Strix lifecycle status, result ingestion, and persisted vulnerability evidence are bound to the same completed run directory.
- Nuclei remains the reviewed active scanner path in the dedicated restricted scanner worker.
- Strix jobs now produce a deterministic execution contract bound to job id, policy fingerprint, scope and request-rate ceiling; broker authorization requires an authenticated contract.
- The Strix boundary now has a broker plus a separate dual-homed read-only egress service; GET/HEAD requests are contract-verified twice, DNS-pinned, public-network-only, non-redirecting, bounded and rate-limited.
- A dedicated inert Strix runner pins v1.6.2, verifies official amd64/arm64 release digests and the exact CLI version at build time, then re-attests the build manifest and extracted binary SHA-256 at runtime without executing the PyInstaller binary; it is attached only to the internal broker network.
- The xbow `xbow-remote-v1` backend hook is verified against the official Strix v1.6.2 Python wheel and registry API; it declares no bind-mount support and intentionally rejects every execution request.
- The isolated runner now exposes authenticated `strix-runner-rpc-v1` on internal port 8092 with strict schemas, HMAC authentication, a 5-second idle socket timeout, a 10-second absolute request-read deadline, a 16-connection concurrency cap, timestamp/nonce replay defenses and no implemented session operations; runner RPC keys must be at least 32 bytes.
- The pinned Strix 1.6.2 Python runtime image is built from attested upstream sources and offline-verified in a non-root, read-only, network-disabled container; `xbow-remote-v1` is registered before the **real** upstream Python interface imports, without invoking the scan entrypoint.
- The remote interface self-test digest is deterministic and excludes random request nonces, while the underlying operation nonces remain random for replay defense.

- The runner now has separate **inert** signed `/v1/session/prepare` and
  `/v1/session/release` metadata operations: an authenticated ticket is
  bound to a contract and manifest digest, sessions get 128-bit random IDs,
  900-second monotonic expiry and bounded concurrency-safe storage.
- A real broker-to-runner integration check covers signed preparation,
  ticket replay rejection, wrong-contract release, release and legacy
  execution blocking.
- A private named Docker volume holds a bounded transactional SQLite journal
  of consumed ticket identities across runner restarts; no manifests are stored.
- The inert runner now checks authenticated, ordered 64 KiB inline file chunks
  against the SHA-256 digests and sizes in the already verified manifest plan;
  only incremental hashes and metadata remain in memory, never file bytes.
- CI proves real broker-to-runner two-chunk verification and fail-closed
  rejection of offset errors, invalid encoding, wrong digests and tampering.

## Broken / blockers
- Active Strix execution is still not wired through the isolated runner/broker path; runner RPC session operations remain unimplemented.
- The standalone Strix binary does not load Python `xbow-remote-v1` registration. The pinned Python bootstrap can import the upstream interface and temporarily bypass two attested Docker-preflight aliases, but **does not invoke the scanner entrypoint**.
- The upstream-compatible RPC create, exec, resolve-port and delete remain unimplemented; inert preparation is **not** a runnable session. Inline file bytes can be streamed and checked in memory, but manifests are never materialized or executed.
- Durable SQLite replay protection was merged via PR #675 on a private named volume; deletion or rollback of this volume remains an operational risk, with active execution still disabled.
- The scanner worker intentionally does not expose a host container socket; do not solve Strix execution by mounting the host Docker socket.

## Manifest-admission hardening (2026-10-18)
- Pre-materialization checks now reject overlapping file/directory entry paths, NUL-containing environment values, invalid UTF-8 text and oversized content before copying buffers.
- The manifest path remains deliberately non-materializing: no host-path reads, uploads, session execution, or target-network I/O are enabled by these checks.
- The CI workflow validates malformed manifests against the real admission module; existing Python, Docker, security and supply-chain gates remain required before merge.

## Current priority
- Manifest ticket v2 with signed 120-second expiry was merged as PR #674 after CI, security and supply-chain success.
- PR #675 merged after CI, security, supply-chain, 2,743 Python tests and a real runner restart proof rejecting previously consumed tickets.
- PR #677 merged after CI, security and supply-chain success: the inert runner verifies canonical manifest-plan bytes, SHA-256 digest, signed counts and one-shot session receipt; no file contents or execution.
- PR #678 merged after 2,743 Python tests, Ruff, Docker broker-to-runner chunk-integrity proof, security and supply-chain success. PR #676 was closed as superseded by the integrated implementation.
- Next implement broker-side orchestration for authenticated manifest plan/file streaming, with per-session lifecycle cleanup and no host bind mounts; keep execution fail-closed until scope and egress enforcement are verified.

## Validation
- PRs #664, #665 and #666 passed CI, security and supply-chain checks before merge: pinned Python runtime image, deterministic remote interface digest, and a real upstream Python import-only proof inside a network-disabled, read-only container.
- PR #666 passed 2,743 existing Python tests; no new unit tests were created. `strix.interface.main` was imported but its scan entrypoint was not invoked.
- PR #484 hardened Strix run-bundle provenance and passed CI, security, supply-chain, Docker builds, Ruff, pytest, and pip-audit before merge.
- Runtime-contract changes require the same full CI/security/supply-chain gates before merge.
- Execution-contract v1 adds deterministic hashing, optional HMAC authentication, policy/job binding, scope checks, rate-cap checks and redacted scan-event tracing.
- Broker isolation is asserted by tests and CI builds the dedicated `strix-broker` Compose profile.
- The read-only egress transport rejects non-public IPs, pins validated DNS results to the socket connection, preserves TLS hostname verification, follows no redirects, bounds responses/timeouts, enforces contract RPS, and allows only one in-flight request per contract.
- Broker readiness now fails closed on the egress service whenever read-only proxying is enabled.
- The Strix runner image pins v1.6.2 release assets/digests and source commit, verifies the archive and exact CLI version during image construction, records that version in the immutable manifest, and re-attests the manifest plus binary SHA-256 at runtime.
- CI verifies the custom backend hook against the official v1.6.2 manylinux x86_64 wheel after checking its pinned SHA-256; the hook self-test proves registration succeeds while backend execution remains blocked.
- The runner RPC contract is independently testable and remains non-executing even if a service instance is constructed with an active flag; the real runner startup attestation still forbids active execution. RPC sockets use a 5-second idle timeout, request headers/body have a 10-second absolute read deadline, truncated bodies are rejected, concurrent connections are capped at 16, and HMAC secrets shorter than 32 bytes are rejected.

## Last verified
- 2026-10-09

<!-- AUTO:START -->
## Automatic repository state

Generated: 2026-10-26T10:17:05Z

### Git
- Branch: `main`
- Head: `e1b738923bc4`
- Commit date: 2026-10-26T06:16:55-04:00
- Commit: security(strix): expire broker-signed manifest admission tickets (#674)
- Tracked files: 692

### Recently changed files
- `.github/workflows/ci.yml`
- `backend/app/strix_broker_models.py`
- `backend/app/strix_runner_manifest_ticket.py`
- `backend/app/strix_runner_rpc.py`
- `backend/tests/test_runtime_capabilities.py`
- `backend/tests/test_strix_runner_rpc.py`
- `docs/strix-inert-session-lifecycle.md`
- `backend/Dockerfile`
- `backend/Dockerfile.scanner`
- `backend/Dockerfile.strix-python-runtime`
- `backend/Dockerfile.strix-runner`
- `backend/app/strix_manifest_admission.py`
- `docker-compose.distributed.yml`
- `docker-compose.tls.yml`
- `frontend/Dockerfile`
- `backend/app/strix_python_bootstrap_runtime.py`
- `docs/strix-python-runtime.md`

### Project signals
- `pyproject.toml`

> Generated by dbrckk/repo-standards. Keep manual priorities and blockers outside the AUTO markers.
<!-- AUTO:END -->
