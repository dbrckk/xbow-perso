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

## Broken / blockers
- Active Strix execution is still not wired through the isolated runner/broker path; runner RPC session operations remain unimplemented.
- The pinned standalone Strix binary does not automatically load the Python `xbow-remote-v1` registration; a pinned Python bootstrap path is still required.
- Strix v1.6.2's Python entrypoint still performs Docker CLI/image preflight before runtime-backend selection can be useful; the bootstrap must address this without exposing a host Docker socket.
- The scanner worker intentionally does not expose a host container socket; do not solve Strix execution by mounting the host Docker socket.

## Current priority
- Keep Strix active dispatch fail-closed while building a reproducible Python Strix v1.6.2 bootstrap that loads `xbow-remote-v1` in the actual runtime process.

## Validation
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
- 2026-10-03

<!-- AUTO:START -->
## Automatic repository state

Generated: 2026-10-06T18:02:59Z

### Git
- Branch: `main`
- Head: `d9a28aa650b3`
- Commit date: 2026-10-06T20:02:47+02:00
- Commit: feat(validation): bind v2 planner to scoped validator gates
- Tracked files: 656

### Recently changed files
- `backend/app/validator.py`
- `backend/tests/test_validator.py`
- `backend/app/kev_catalog.py`
- `backend/tests/test_kev_catalog.py`
- `backend/app/cve_risk_context.py`
- `backend/app/finding_intelligence.py`
- `backend/app/validation_priority.py`
- `backend/tests/test_cve_risk_context.py`
- `backend/tests/test_finding_intelligence.py`
- `backend/tests/test_validation_priority.py`
- `backend/app/active_validation.py`
- `backend/tests/test_active_validation.py`

### Project signals
- `pyproject.toml`

> Generated by dbrckk/repo-standards. Keep manual priorities and blockers outside the AUTO markers.
<!-- AUTO:END -->
