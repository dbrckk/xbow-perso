# Release integrity

Release container images are produced only by the tag-triggered GitHub Actions workflow.

## Release flow

A tag matching `v*` builds the backend and frontend independently and publishes them to GHCR.

Each published image receives:

- an immutable image digest;
- BuildKit SBOM metadata;
- maximum-mode build provenance;
- a GitHub build-provenance attestation bound to the published digest;
- a small release artifact containing the exact `image@sha256:...` deployment reference.

Production deployment must use the digest references emitted by this workflow. Version tags exist for discovery and release navigation; they are not the production integrity boundary.

## Verification

Before production rollout:

1. obtain the backend and frontend digest references from the release workflow artifacts;
2. verify the GitHub artifact attestation for each published image against this repository;
3. configure `XBOW_BACKEND_IMAGE` and `XBOW_FRONTEND_IMAGE` with the verified digest references;
4. run the deployment preflight;
5. deploy only when preflight reports no integrity error.

Example verification with GitHub CLI:

```bash
gh attestation verify \
  oci://ghcr.io/OWNER/xbow-perso-backend@sha256:DIGEST \
  --repo OWNER/xbow-perso
```

Repeat for the frontend image.

## Failure policy

Do not deploy when:

- an image is referenced only by a mutable tag;
- the digest does not match the reviewed release;
- provenance verification fails;
- the attestation belongs to another repository;
- deployment preflight reports an integrity error.

A failed verification requires investigation or a new release. It must not be bypassed by substituting a mutable tag.
