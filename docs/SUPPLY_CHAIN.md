# Supply-chain security

xbow-perso treats its build inputs and produced container images as part of the security boundary.

## Current controls

- Python runtime dependencies are explicitly versioned in `backend/requirements.txt`.
- Development and CI dependencies are explicitly versioned in `backend/requirements-dev.txt`.
- Dependency vulnerabilities are checked by `pip-audit`.
- Repository history is scanned for accidentally committed secrets.
- Dependabot tracks Python, GitHub Actions, and Docker dependency updates.
- Docker build context excludes local credentials, runtime databases, vault data, backups, caches, and editor metadata.
- CI produces a CycloneDX SBOM for the backend dependency set and uploads it as a build artifact.

## Operator requirements

Never treat a mutable image tag as an integrity guarantee. Production deployments should pin externally sourced images by digest after validating the desired release in a staging environment.

Do not copy local `.env` files, private keys, vault files, database snapshots, or scanner output into an image build context.

Review dependency updates before merging. Automated update proposals are maintenance inputs, not an authorization to deploy.

## Planned hardening

- publish signed release images;
- attach SBOM and provenance attestations to release artifacts;
- verify approved image digests during deployment preflight;
- maintain a documented dependency-update and emergency-rotation procedure.
