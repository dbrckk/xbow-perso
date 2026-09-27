# Offensive expansion roadmap

This roadmap incorporates the requested expansion areas while preserving the existing authorization, scope, rate, non-destructive, sandbox, and human-review controls.

## Already integrated

- Recon and mapping: Subfinder, HTTPX and Katana are part of the bounded external recon path; Nuclei is the reviewed active scanner path.
- AI-assisted prioritization: adaptive planning, decision consensus, campaign-risk, coverage, temporal novelty, confidence and high-value intelligence already provide advisory prioritization.
- Contextual report generation: reports are evidence-backed and still require human review.
- Knowledge graph/correlation: the durable ObservationGraph links assets, endpoints, forms, technologies, findings, evidence and validation. A separate Neo4j deployment is not required for the current single-node architecture.
- Automated workflows: the orchestrator already chains inventory/recon, scan, independent validation and reporting under fail-closed gates.

## Added in this expansion

### OpenAPI / Swagger test generation

POST /api/testing/openapi/preview accepts an OpenAPI/Swagger document and generates bounded test cases for GET, HEAD and OPTIONS only.

The preview:

- sends zero network requests;
- never generates mutating requests;
- never invents exploit payloads;
- is capped at 250 paths and 500 cases;
- records whether authentication is declared;
- is preview_only and advisory.

This provides the safe part of specification-driven API testing without importing an executable offensive dependency.

### Capability catalog

GET /api/testing/offensive-expansion exposes the requested expansion state without changing execution authority.

## Planned, preview-only until a dedicated safety contract exists

- Amass as an additional recon adapter.
- ffuf / Wfuzz for bounded discovery/fuzz planning.
- SQLMap / Metasploit for controlled validation planning.
- Additional API-security reasoning for SSRF, IDOR, JWT/OAuth and related classes.

These remain preview_only until each has:

1. exact campaign scope binding;
2. method/action allowlists;
3. explicit rate and request budgets;
4. sandbox/runtime attestation;
5. deterministic evidence capture;
6. independent validation;
7. a human approval gate for any non-read-only action.

No item in this roadmap enables credential attacks, denial of service, destructive testing, social engineering, arbitrary shell execution, or out-of-scope activity.
