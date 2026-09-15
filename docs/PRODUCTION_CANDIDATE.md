# Production candidate gate

Publishing a container image and approving it for production are separate operations.

## Gate inputs

The release-quality workflow accepts only explicit backend and frontend image references. Both must use an immutable `@sha256:` digest.

It also requires the exact release tag or commit to validate.

## Required checks

A production candidate passes only when all of these succeed:

- both image references are digest-pinned;
- both image provenance attestations verify against this repository;
- the requested release source can be checked out;
- Python dependency consistency passes;
- the backend test suite passes with active scanning disabled;
- Ruff static checks pass;
- runtime dependency vulnerability auditing passes.

The workflow emits a retained candidate manifest containing the release reference, immutable image references, and validated commit.

## Environment approval

The workflow uses the GitHub environment named `production-candidate`.

Repository administrators should configure that environment with required reviewers. This makes candidate approval an explicit repository policy rather than an implicit consequence of pushing a tag.

No production secrets are required by this gate.

## Promotion policy

A release is production-eligible only after:

1. the release-images workflow publishes and attests both images;
2. their immutable digest references are supplied to the release-quality gate;
3. the gate completes successfully;
4. the candidate manifest is retained as deployment evidence;
5. production deployment preflight accepts the same digest references.

Do not replace a failed candidate with a mutable image tag or skip provenance verification.
