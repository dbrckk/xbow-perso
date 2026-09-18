# HackerOne Control Center Design

## Goal

Turn the existing manual HackerOne launcher into a mobile-first control center that can read HackerOne program metadata and structured scope directly from the official Hacker API while preserving xbow-perso's fail-closed admission model.

## Safety model

- HackerOne credentials remain server-side only.
- The integration is read-only against HackerOne in this tranche.
- Remote data never grants scanning permission by inference. The operator must still explicitly confirm that automation/scanning is authorized and provide the reviewed program request-rate limit.
- Destructive testing, denial of service, social engineering, and credential attacks remain hard-disabled.
- Unsupported or conflicting scope assets block admission.
- A remote snapshot fingerprint is bound to the local preview. Launch re-fetches the HackerOne snapshot and returns a conflict if the remote program/scope changed after review.
- HTTPS only, fixed HackerOne API origin, redirects refused, bounded response sizes, bounded timeouts, and no credential-bearing logs.

## Official HackerOne API endpoints

The implementation uses the Hacker API v1 endpoints documented by HackerOne:

- `GET /v1/hackers/programs`
- `GET /v1/hackers/programs/{handle}`
- `GET /v1/hackers/programs/{handle}/structured_scopes`
- `GET /v1/hackers/programs/{handle}/scope_exclusions`

Pagination uses `page[number]` and `page[size]` with a page size of 100 and a conservative maximum page count.

## Credentials

Resolve two secrets through the existing vault abstraction:

- vault `hackerone_api_username` / env `XBOW_HACKERONE_API_USERNAME`
- vault `hackerone_api_token` / env `XBOW_HACKERONE_API_TOKEN`

When vault mode is enabled, environment fallback remains forbidden by the existing `resolve_secret()` contract.

## Backend API

Add read-only local endpoints:

- `GET /api/imports/hackerone/connection` — configured/not configured only; never returns credentials.
- `GET /api/imports/hackerone/programs` — normalized program picker data.
- `GET /api/imports/hackerone/programs/{handle}/snapshot` — program metadata, complete structured scope, scope exclusions, normalized import preview, and deterministic snapshot SHA-256.

Extend preview and launch payloads with optional HackerOne remote binding fields:

- `remote_handle`
- `remote_snapshot_sha256`

When those fields are present, preview validates that the supplied scope document matches the fetched remote snapshot. Launch re-fetches HackerOne and returns HTTP 409 with reason `stale_hackerone_snapshot` if the snapshot hash differs.

Existing fully manual JSON mode remains supported for offline/legacy operation.

## Frontend

Enhance the existing `frontend/hackerone.js` launcher rather than introducing a new framework.

Add:

- connection status pill;
- searchable program selector;
- `Load HackerOne program` action;
- program metadata summary: submission state, safe-harbor signal, bounty/open-scope flags;
- normalized scope table with asset identifier/type/eligibility and local compatibility status;
- scope exclusion summary;
- remote snapshot fingerprint display;
- preflight state that becomes invalid whenever the selected program or local policy fields change.

The UI must never display or accept HackerOne API credentials.

## Launch semantics

1. Operator loads a HackerOne program.
2. Backend fetches all pages of the remote program scope and exclusions.
3. UI populates the StructuredScope JSON from that trusted server response.
4. Operator reviews policy text on HackerOne and explicitly fills the local policy fields that HackerOne does not structure as machine-enforceable authorization.
5. Existing rules-preview endpoint validates the local policy and scope.
6. Preview stores both the local payload fingerprint and remote snapshot hash.
7. Launch re-fetches the remote snapshot server-side.
8. Any drift blocks launch and requires a fresh review.
9. A matching snapshot proceeds through the existing conservative campaign admission path and starts the campaign.

## Non-goals

- No automatic vulnerability submission to HackerOne.
- No automatic interpretation of free-form policy text as permission.
- No bypass of test-account constraints or additional restrictions.
- No automatic enabling of Nuclei/PentAGI runtime feature flags.
- No write operations against HackerOne.