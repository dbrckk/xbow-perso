from __future__ import annotations

from typing import Any, Literal

from .main import Campaign

ReportPlatform = Literal["generic", "hackerone", "bugcrowd"]


def render_markdown(
    campaign: Campaign,
    platform: ReportPlatform = "generic",
    *,
    evidence_quality: dict[str, Any] | None = None,
    governance_manifest: dict[str, Any] | None = None,
) -> str:
    """Render a human-review draft from independently confirmed findings only."""
    confirmed = [f for f in campaign.findings if f.status == "confirmed"]
    platform_name = {"generic": "Security program", "hackerone": "HackerOne", "bugcrowd": "Bugcrowd"}[platform]
    severity_counts = {level: sum(1 for f in confirmed if f.severity == level) for level in ("critical", "high", "medium", "low", "info")}
    quality_by_id = evidence_quality or {}
    high_quality = sum(
        1
        for finding in confirmed
        if str((quality_by_id.get(str(finding.id)) or {}).get("grade") or "") == "high"
    )

    lines = [
        f"# Security report draft — {campaign.target.name}",
        "",
        "> **Human approval required before external submission.**",
        "",
        f"**Submission format:** {platform_name}  ",
        f"**Campaign ID:** `{campaign.id}`  ",
        f"**Target:** {campaign.target.primary_url}  ",
        f"**Authorization reference:** {campaign.target.rules.authorization_reference}  ",
        "",
        *(
            [
                "## Governance & audit manifest",
                "",
                f"- **Schema:** {governance_manifest.get('schema', 'N/A')}",
                f"- **Reporting governance fingerprint:** `{governance_manifest.get('governance_fingerprint', 'N/A')}`",
                f"- **Provenance fingerprint:** `{governance_manifest.get('provenance_fingerprint', 'N/A')}`",
                f"- **Governance verification:** {'VALID' if governance_manifest.get('verification_valid') else 'INVALID'}",
                f"- **Findings represented:** {governance_manifest.get('findings', 0)}",
                f"- **Submission-ready findings:** {governance_manifest.get('submission_ready', 0)}",
                "",
                "> This manifest is read-only. Any governance-state change after generation requires renewed human review before submission.",
                "",
            ]
            if governance_manifest is not None
            else []
        ),
        "## Executive summary",
        "",
        f"{len(confirmed)} independently validated finding(s) are eligible for human review.",
        *(
            [
                f"{high_quality} of {len(confirmed)} confirmed finding(s) currently meet the high-quality evidence threshold.",
                "",
            ]
            if evidence_quality is not None
            else []
        ),
        "| Severity | Count |",
        "| --- | ---: |",
        *[f"| {level.title()} | {severity_counts[level]} |" for level in ("critical", "high", "medium", "low", "info")],
        "",
        "## Scope",
        "",
        "### In scope",
        *[f"- `{x}`" for x in campaign.target.rules.allowed_targets],
        "",
        "### Explicit exclusions",
        *([f"- `{x}`" for x in campaign.target.rules.denied_targets] or ["- None declared"]),
        "",
        "## Submission candidates",
        "",
    ]
    if not confirmed:
        lines.append("No independently validated vulnerabilities are currently available for submission.")

    for index, finding in enumerate(confirmed, 1):
        quality = quality_by_id.get(str(finding.id)) if evidence_quality is not None else None
        quality_grade = str((quality or {}).get("grade") or "unknown")
        quality_score = float((quality or {}).get("score") or 0.0)
        submission_ready = quality_grade == "high" if evidence_quality is not None else None
        lines += [
            f"### {index}. {finding.title}",
            "",
            "#### Submission metadata",
            "",
            f"- **Severity:** {finding.severity.upper()}",
            f"- **Asset:** `{finding.asset}`",
            f"- **Endpoint:** `{finding.endpoint or 'N/A'}`",
            f"- **Weakness / CWE:** {finding.cwe or 'N/A'}",
            f"- **CVSS:** {finding.cvss if finding.cvss is not None else 'N/A'}",
            f"- **Discovery engine:** {finding.discovered_by}",
            f"- **Independent validator:** {finding.validated_by or 'N/A'}",
            *(
                [
                    f"- **Evidence quality:** {quality_grade.upper()} ({round(quality_score * 100)}%)",
                    (
                        "- **Submission readiness:** READY FOR HUMAN SUBMISSION REVIEW"
                        if submission_ready
                        else "- **Submission readiness:** HOLD — strengthen evidence before submission"
                    ),
                ]
                if evidence_quality is not None
                else []
            ),
            "",
            "#### Summary",
            "",
            finding.summary or "No summary recorded.",
            "",
            "#### Security impact",
            "",
            finding.impact or "Impact requires analyst completion before submission.",
            "",
            "#### Steps to reproduce",
            "",
            *([f"{n}. {step}" for n, step in enumerate(finding.reproduction_steps, 1)] or ["Reproduction steps were not recorded."]),
            "",
            "#### Evidence",
            "",
            *([f"- {item}" for item in finding.evidence] or ["- Evidence is stored as integrity-checked campaign artifacts."]),
            "",
            "#### Suggested remediation",
            "",
            finding.remediation or "Remediation guidance requires analyst completion.",
            "",
        ]

    lines += [
        "## Testing constraints",
        "",
        f"- Maximum configured request rate: {campaign.target.rules.max_requests_per_second} requests/second",
        "- Destructive testing by autonomous workers: prohibited",
        "- Denial of service by autonomous workers: prohibited",
        "- Social engineering by autonomous workers: prohibited",
        "- Credential attacks by autonomous workers: prohibited",
        "",
        "## Methodology and evidence integrity",
        "",
        "Automated discovery is separated from independent validation. Only findings explicitly marked confirmed by a validator different from the discovery engine are included. Evidence artifacts are stored with recorded size and SHA-256 and are verified on retrieval.",
        *(
            [
                "Evidence-quality grades are advisory and explain whether the recorded validation chain, corroboration, source diversity, and artifact provenance are strong enough for submission review. A confirmed finding below HIGH remains in the draft but is explicitly held from submission readiness.",
            ]
            if evidence_quality is not None
            else []
        ),
        "",
        "## Submission checklist",
        "",
        "- Obtain explicit human approval for the exact report artifact before any external submission.",
        "- Confirm the affected asset remains in the current program scope before submission.",
        "- Re-check program-specific disclosure rules and duplicate handling requirements.",
        "- Remove secrets, authentication tokens, and unrelated personal data from attached evidence.",
        "- Attach only the minimum evidence required to reproduce the issue safely.",
    ]
    return "\n".join(lines)
