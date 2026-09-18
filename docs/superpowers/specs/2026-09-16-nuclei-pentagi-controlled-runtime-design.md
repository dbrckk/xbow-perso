# Nuclei + PentAGI Controlled Runtime Design

## Goal
Make Nuclei executable in the dedicated scanner sandbox and promote PentAGI from preview-only to an active orchestrator without granting PentAGI unrestricted target access.

## Security boundary
XBOW remains the authority for campaign scope, rate, prohibited actions, cancellation and evidence. PentAGI may plan and request work but must not bypass XBOW policy. HackerOne/program rules remain the source of authorization.

## Nuclei runtime
- Build a dedicated scanner image rather than adding Nuclei to the control-plane image.
- Pin Nuclei to v3.11.1 and verify the upstream SHA-256 for each supported Linux architecture during image build.
- Pin nuclei-templates to v10.4.8 and make template provenance/version observable.
- Keep the scanner container read-only, no-new-privileges, cap-drop ALL, and behind the scanner Compose profile.
- Fail closed when the runtime version differs from XBOW_NUCLEI_ALLOWED_VERSION.

## PentAGI execution contract
- PentAGI is an orchestrator, not an unrestricted execution plane.
- Replace preview-only planning with an explicitly execution-capable plan only when the controlled-tool contract is configured.
- Create PentAGI flows with built-in direct network-capable functions disabled for XBOW-managed flows.
- Expose only XBOW-mediated asynchronous operations to PentAGI. Requests return job identifiers; XBOW workers perform the actual authorized network action.
- Bind every remote flow to one XBOW campaign using server-held metadata; do not trust a campaign identifier supplied by the remote agent.
- Revalidate campaign state, target scope, policy fingerprint, prohibited actions and rate ceiling immediately before each queued action.
- Campaign cancellation prevents new actions and requests remote flow stop.
- Preserve one-shot create semantics: no automatic retry after ambiguous remote create failures.

## Transport and credentials
- HTTPS only, no redirects, bounded request/response sizes and deadlines.
- PentAGI API credentials remain server-side/vault-backed and never appear in flow prompts, artifacts or UI.
- Treat remote flow IDs as untrusted identifiers and validate response shapes.

## Evidence and lifecycle
- Persist creation receipts and status artifacts.
- Normalize completed XBOW-mediated results into the existing observation/finding/evidence pipeline.
- Audit every PentAGI-requested action with campaign binding and policy fingerprint.

## Rollout
- Default all active flags off.
- Dry-run remains the default.
- Add capabilities/readiness reasons for missing Nuclei runtime, PentAGI controlled-tool contract, credentials and worker gates.
- Document exact opt-in environment variables.

## Tests
- Docker/runtime contract tests for pinned Nuclei and templates.
- Admission tests proving PentAGI remains denied when direct tools are enabled, binding is absent, policy changes, campaign is cancelled, rate exceeds the cap, or dry-run is enabled.
- Transport tests for HTTPS, redirects, auth, malformed responses and ambiguous failures.
- Queue tests for dedupe/no retry.
- End-to-end dry-run tests and CI syntax/build checks.
