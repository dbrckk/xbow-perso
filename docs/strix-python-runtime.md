# Strix Python 1.6.2 — inert runtime image

This image packages the **official pinned Strix Python wheel** alongside the
`xbow-remote-v1` registration and the existing attested preflight/bootstrap
compatibility modules. It is a reproducible dependency and integration check,
**not** a scanner and **not** an active Strix runner.

## Build

```bash
docker build --pull -f backend/Dockerfile.strix-python-runtime \
  -t xbow-strix-python-runtime:local backend
```

The build downloads Python 3.12.14, uv 0.12.10, the Strix 1.6.2 source lock,
and the official Strix wheel, and verifies pinned hashes/source identities.
The Python base is pinned by OCI digest. Do not replace the base or upstream
artifact hashes without verifying new immutable identities.

## Offline, read-only checks

```bash
docker run --rm --network none --read-only \
  --tmpfs /tmp:size=16m,noexec,nosuid,nodev \
  --cap-drop ALL --pids-limit 128 \
  --security-opt no-new-privileges:true \
  xbow-strix-python-runtime:local
```

The default command runs the bootstrap self-check without invoking the Strix
scan entrypoint. CI additionally runs the pinned backend registration and
upstream compatibility checks as independent probes.

CI also performs a **real import** of the pinned upstream
`strix.interface.main` and `strix.interface.environment` modules. This is
not an execution of `main()` or a scan. The bootstrap registers the
`xbow-remote-v1` backend before importing the upstream interface, checks
that only the two Docker-preflight aliases are temporarily bypassed, and
verifies the original upstream callables are restored afterwards.

To reproduce that isolated import check after building the image:

```bash
docker run --rm --network none --read-only \
  --tmpfs /tmp:size=16m,noexec,nosuid,nodev \
  --cap-drop ALL --pids-limit 128 \
  --security-opt no-new-privileges:true \
  xbow-strix-python-runtime:local \
  /opt/strix-python/.venv/bin/python \
  -m app.strix_python_bootstrap_runtime --verify-upstream-import
```

## Explicit limitations

- No target or internet traffic: runtime verification uses `--network none`.
- No host Docker socket, bind mounts, ports, or writable root filesystem.
- The `xbow-remote-v1` session methods are deliberately non-executable;
  no session creation, command execution, or manifest upload is enabled.
- The regular bootstrap self-test remains synthetic. The additional CI probe
  imports the real upstream interface but does **not** invoke `main()`, execute
  a scan, connect to a broker, or establish a runnable Strix session.
- A successful import is **not** proof of active Strix scanning support.
- Nuclei remains the independently gated active-scanning path for scopes
  explicitly authorizing automation.

Next: complete authenticated runner session lifecycle with
strict allowlisted manifests and policy-bound request budgets. Keep active
Strix dispatch fail-closed until those components pass end-to-end checks.
