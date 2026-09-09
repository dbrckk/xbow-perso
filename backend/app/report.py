from __future__ import annotations

from typing import Literal

from .main import Campaign

ReportPlatform = Literal["generic", "hackerone", "bugcrowd"]


def render_markdown(campaign: Campaign, platform: ReportPlatform = "generic") -> str:
    """Render a human-review draft from independently confirmed findings only."""
    confirmed = [f for f in campaign.findings if f.status == "confirmed"]
    platform_name = {"generic": "Security program", "hackerone": "HackerOne", "bugcrowd": "Bugcrowd"}[platform]
    severity_counts = {level: sum(1 for f in confirmed if f.severity == level) for level in ("critical", "high", "medium", "low", "info")}

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
        "## Executive summary",
        "",
        f"{len(confirmed)} independently validated finding(s) are eligible for human review.",
        "",
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
