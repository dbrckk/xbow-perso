# Active Validation v2 — Design

Date: 2026-09-16
Status: Design approved in chat; implementation not started
Repository: `dbrckk/xbow-perso`

## 1. Purpose

Active Validation v2 extends the existing bounded validator so it can collect higher-quality offensive evidence for authorized HackerOne bug bounty targets without turning XBOW into an exploitation engine.

The feature remains conservative by design:

- every request must target a host already admitted by the campaign scope policy;
- active validation remains disabled by default;
- execution is limited to non-destructive `GET` and `HEAD` requests;
- redirects are never followed;
- only existing query parameters may be mutated;
- mutations use inert markers or inert reserved destinations;
- no credentials, credential attacks, social engineering, denial of service, destructive actions, persistence, or automatic vulnerability submission are introduced;
- output is evidence and prioritization metadata, never an automatic claim that a vulnerability is confirmed.

The immediate goal is better evidence for three bug-bounty-relevant classes of observations:

1. parameter reflection and response differentials;
2. CORS policy behavior;
3. open-redirect behavior.

## 2. Current baseline

The current validator already provides the most important safety primitives:

- explicit HTTP(S) URL validation;
- campaign host allow/deny checks;
- optional active validation behind `XBOW_ENABLE_HTTP_VALIDATION`;
- optional differential validation behind `XBOW_ENABLE_DIFFERENTIAL_VALIDATION`;
- rate limiting based on campaign policy;
- no redirect following;
- bounded timeouts and response previews;
- redaction of query values in persisted evidence;
- one inert mutation of the first existing query parameter;
- conservative `none` / `weak` / `strong` differential intelligence.

The main limitation is that the current differential path evaluates only one parameter and one mutation pattern. Active Validation v2 should generalize that flow while preserving its safety model.

## 3. Scope of v2

### Included

- a reusable safe-probe planning layer;
- a bounded request budget per validation run;
- parameter-by-parameter inert differential probes;
- passive response-header inspection;
- a synthetic benign Origin probe for CORS behavior;
- an inert reserved destination probe for redirect-like parameters;
- normalized validation signals that integrate with existing differential intelligence;
- provenance sufficient to trace each signal to its validation observation;
- deterministic tests that require no real target.

### Explicitly excluded

- payload execution;
- JavaScript execution or browser exploit validation;
- credential or session theft simulation;
- authentication bypass attempts;
- IDOR / multi-account authorization testing;
- SSRF chaining;
- file upload or command execution probes;
- POST, PUT, PATCH, DELETE, OPTIONS, TRACE, CONNECT, or WebSocket mutation flows;
- redirect chasing;
- automatic report submission;
- automatic finding confirmation.

These exclusions are deliberate. Future offensive modules can be designed separately so each capability has its own scope and safety contract.

## 4. Architecture

### 4.1 New module: `backend/app/active_validation.py`

This module owns planning and signal extraction. It must not perform network I/O itself.

Primary responsibilities:

- build a bounded `SafeProbePlan` from an already scoped finding/endpoint;
- select existing query parameters for inert differential checks;
- identify redirect-like parameter names using a conservative allowlist;
- define an optional synthetic Origin request for CORS behavior;
- define deterministic inert markers;
- normalize response metadata into validation signals;
- enforce per-run request-budget accounting before requests reach the executor.

Suggested core types:

```text
SafeProbePlan
  finding_id
  target_url
  probes[]
  max_requests

SafeProbe
  kind
  method
  url
  headers
  parameter
  marker

ValidationSignal
  kind
  strength
  parameter
  evidence
  reason
```

`active_validation.py` is pure planning/analysis logic so it can be exhaustively unit-tested without network access.

### 4.2 Existing module: `backend/app/validator.py`

`validator.py` remains the only network executor for this feature.

It keeps responsibility for:

- feature gates;
- URL parsing and scheme checks;
- campaign scope checks;
- rate limiting;
- request timeout and byte limits;
- no-redirect transport;
- response truncation;
- redaction before persistence.

The validator will execute only probes emitted by `active_validation.py`, and only after independently re-validating the probe target against the existing scope checker. Planning must never be trusted as the sole scope control.

### 4.3 Existing module: `backend/app/differential_intelligence.py`

The current differential intelligence layer will be extended to understand multiple normalized signal kinds while retaining the existing conservative signal ladder.

The invariant remains:

- `none`: no meaningful validation evidence;
- `weak`: response changed in a way worth review;
- `strong`: deterministic behavior closely tied to the inert probe;

`strong` still means strong validation evidence, not confirmed exploitability.

### 4.4 Existing decision and finding intelligence

`finding_intelligence.py` and `red_team_decision.py` may surface the new signal kinds for human review prioritization.

No change in execution authority is introduced. `red_team_decision.py` remains advisory-only and must not autonomously trigger active probes.

## 5. Probe model

### 5.1 Multi-parameter inert differential probes

For a target URL containing existing query parameters, the planner may create one probe per selected parameter up to a hard cap.

Rules:

- only parameters already present in the URL are eligible;
- names are preserved;
- one value is replaced at a time;
- marker format is deterministic and inert, e.g. `xbowv2-<short-hash>`;
- no metacharacter or executable payload corpus is used;
- duplicate parameter names are handled deterministically;
- original values are never persisted in evidence;
- planner stops when the per-run request budget is reached.

Signals can include:

- HTTP status changed;
- content type changed;
- body hash changed;
- response length changed beyond a conservative threshold;
- exact inert marker reflected;
- marker reflection context category when it can be determined without injecting syntax.

Context classification is informational only, such as `html_text`, `html_attribute`, `script_text`, `json_string`, or `unknown`. It must not escalate a finding to confirmed XSS.

### 5.2 CORS behavior probe

The CORS probe uses a synthetic reserved origin such as:

`https://xbow.invalid`

The target request remains in scope. The synthetic Origin is only an HTTP request header; no request is made to the `.invalid` host.

The executor performs the scoped target request and records selected CORS response headers:

- `Access-Control-Allow-Origin`;
- `Access-Control-Allow-Credentials`;
- `Vary` when relevant.

Possible signals:

- origin reflected exactly;
- wildcard origin observed;
- credentials allowed;
- reflected origin plus credentials allowed;
- baseline and synthetic-Origin behavior differ.

These are policy-behavior signals only. The validator must not attach real cookies, tokens, browser credentials, or victim sessions for the purpose of proving data theft.

### 5.3 Open-redirect behavior probe

Only existing parameters with conservative redirect-like names are eligible, for example:

- `redirect`;
- `redirect_uri`;
- `return`;
- `return_url`;
- `next`;
- `continue`;
- `url`;
- `target`;
- `destination`.

The replacement destination uses a reserved inert HTTPS host such as:

`https://xbow.invalid/redirect-check`

The validator never follows the redirect.

A strong redirect signal requires the target response itself to return a redirect status and a `Location` header that resolves to the exact inert destination or an unambiguous transformation of it.

The system does not request the destination and does not chain the redirect into another vulnerability class.

## 6. Feature gates and budgets

Existing gates remain mandatory:

- `XBOW_ENABLE_HTTP_VALIDATION`;
- `XBOW_ENABLE_DIFFERENTIAL_VALIDATION`.

V2 adds independent gates, all defaulting to disabled:

- `XBOW_ENABLE_PARAMETER_VALIDATION_V2`;
- `XBOW_ENABLE_CORS_VALIDATION`;
- `XBOW_ENABLE_REDIRECT_VALIDATION`.

Recommended bounded configuration:

- `XBOW_VALIDATION_MAX_PARAMETERS`: default 5, hard maximum 10;
- `XBOW_VALIDATION_MAX_REQUESTS`: default 8, hard maximum 16;
- existing timeout and byte limits remain authoritative;
- campaign `max_requests_per_second` remains authoritative;
- local validation RPS must never exceed campaign policy.

If a budget is exhausted, remaining probes are skipped with an explicit reason recorded in local validation metadata.

## 7. Scope and HackerOne policy contract

A probe is eligible only when all of the following are true:

1. the campaign is backed by a human-reviewed HackerOne policy snapshot;
2. automated scanning is allowed by that policy snapshot;
3. the target URL resolves to an explicitly allowed campaign host;
4. the target is not denied by campaign policy;
5. active validation gates are enabled by the operator;
6. the requested probe kind is enabled;
7. request and rate budgets remain available.

`additional_restrictions` stays human-reviewed text. V2 must not attempt to infer permission from ambiguous free text.

If scope or permission is ambiguous, the probe is skipped rather than attempted.

## 8. Evidence and persistence

Persist only the minimum needed to review the signal:

- finding ID;
- sanitized URL without query values;
- parameter name;
- probe kind;
- response status;
- selected response headers;
- truncated/redacted preview when already allowed by the validator;
- content hash / length metadata;
- boolean differential flags;
- signal strength;
- observation/provenance IDs.

Do not persist:

- raw original query values;
- authentication secrets;
- cookies;
- authorization headers;
- full unbounded response bodies;
- synthetic headers that contain secrets.

The existing query-value redaction path must remain in force for all v2 response previews.

## 9. Error handling

Every probe returns a structured outcome rather than throwing target-specific failures through the validation pipeline.

Expected outcomes include:

- `ok`;
- `dry_run`;
- `out_of_scope`;
- `gate_disabled`;
- `budget_exhausted`;
- `unsupported_method`;
- `network_error`;
- `timeout`;
- `response_too_large`;
- `not_eligible`.

One failed probe must not cause remaining safe probes to run outside their budget, nor should it promote a finding.

## 10. Data flow

```text
Finding / endpoint
    |
    v
existing validator scope resolution
    |
    v
SafeProbePlan (pure, bounded)
    |
    v
validator re-checks scope + gates + budget
    |
    v
GET/HEAD request, no redirects
    |
    v
sanitized ProbeResult
    |
    v
active validation signal extraction
    |
    v
differential intelligence + observation graph
    |
    v
finding intelligence / review prioritization
```

No arrow in this flow leads to automatic exploitation or automatic HackerOne submission.

## 11. Testing strategy

Implementation follows TDD. Tests are added before production behavior.

### Unit tests: planning

- no probes when the URL has no eligible surface;
- only existing query parameters are mutated;
- one parameter changes per probe;
- deterministic markers;
- duplicate parameter handling;
- parameter cap enforced;
- request budget enforced;
- redirect-like allowlist enforced;
- inert destination is reserved and fixed;
- no unsupported HTTP method can be planned.

### Unit tests: CORS analysis

- reflected synthetic Origin signal;
- wildcard ACAO signal;
- `Access-Control-Allow-Credentials: true` parsing;
- reflected Origin plus credentials produces strong review evidence;
- absence of CORS headers yields no signal;
- no request attempts to `xbow.invalid`.

### Unit tests: redirect analysis

- 3xx plus exact inert `Location` produces a strong redirect signal;
- relative/local redirect does not falsely match external destination;
- non-redirect status does not produce a strong signal;
- destination is never followed.

### Unit tests: differential evidence

- status delta classified conservatively;
- body delta classified conservatively;
- exact inert marker reflection classified strongly;
- context metadata does not equal exploit confirmation;
- multiple observations preserve provenance;
- strongest signal wins without dropping contributing observation IDs.

### Integration tests

- all active gates disabled means zero active network calls;
- out-of-scope host means zero active network calls;
- campaign rate limit is respected;
- no redirects are followed;
- sensitive query values are redacted from persisted previews;
- request count never exceeds configured budget;
- no result automatically marks a finding confirmed;
- no result triggers automatic submission.

Tests should use local fakes/mocks rather than public targets.

## 12. Implementation decomposition

### Block 1 — Safe probe framework + multi-parameter differential

Create the pure planning/signal module, request-budget contract, and parameter-by-parameter inert differential probes. Integrate with the existing validator and differential intelligence.

### Block 2 — CORS evidence

Add the synthetic-Origin probe and normalized CORS signals behind its own disabled-by-default gate.

### Block 3 — Redirect evidence

Add redirect-like parameter selection and inert `.invalid` destination checks without following redirects.

### Block 4 — Intelligence integration

Surface normalized signal kinds in finding intelligence and review prioritization while keeping red-team decisions advisory-only.

Each block must pass its focused tests before the next block begins.

## 13. Success criteria

Active Validation v2 is complete when:

- the existing safety guarantees remain intact;
- all new active behavior is disabled by default;
- every active request is scope checked immediately before execution;
- request/rate budgets are enforced centrally;
- parameter reflection, CORS, and redirect behavior can produce structured evidence;
- no redirect is followed;
- no unsupported HTTP method is emitted;
- no real credential/session material is introduced for validation;
- differential intelligence can consume multiple v2 observations conservatively;
- provenance remains traceable;
- findings are prioritized for review but never auto-confirmed;
- automated HackerOne submission remains absent;
- all unit and integration tests pass.

## 14. Non-goals for this cycle

The following require separate designs and approvals:

- authenticated multi-account authorization / IDOR validation;
- browser-executed XSS confirmation;
- SSRF confirmation beyond inert response evidence;
- file-upload validation;
- command injection / RCE validation;
- credential workflows;
- autonomous exploit chaining;
- autonomous report submission.
