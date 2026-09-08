from __future__ import annotations

from .main import Campaign


def render_markdown(campaign: Campaign) -> str:
    confirmed = [f for f in campaign.findings if f.status == "confirmed"]
    lines = [
        f"# Security Assessment — {campaign.target.name}",
        "",
        f"**Campaign ID:** `{campaign.id}`  ",
        f"**Target:** {campaign.target.primary_url}  ",
        f"**Authorization reference:** {campaign.target.rules.authorization_reference}  ",
        "",
        "## Executive summary",
        "",
        f"{len(confirmed)} independently validated finding(s) are included in this report.",
        "",
        "## Scope",
        "",
        "### In scope",
        *[f"- `{x}`" for x in campaign.target.rules.allowed_targets],
        "",
        "### Explicit exclusions",
        *([f"- `{x}`" for x in campaign.target.rules.denied_targets] or ["- None declared"]),
        "",
        "## Findings",
        "",
    ]
    if not confirmed:
        lines.append("No independently validated vulnerabilities are currently available for submission.")

    for index, finding in enumerate(confirmed, 1):
        lines += [
            f"### {index}. {finding.title}",
            "",
            f"**Severity:** {finding.severity.upper()}  ",
            f"**Asset:** `{finding.asset}`  ",
            f"**Endpoint:** `{finding.endpoint or 'N/A'}`  ",
            f"**CWE:** {finding.cwe or 'N/A'}  ",
            f"**CVSS:** {finding.cvss if finding.cvss is not None else 'N/A'}  ",
            "",
            "#### Summary",
            finding.summary,
            "",
            "#### Security impact",
            finding.impact or "Impact requires analyst completion.",
            "",
            "#### Steps to reproduce",
            *([f"{n}. {step}" for n, step in enumerate(finding.reproduction_steps, 1)] or ["Reproduction steps were not recorded."]),
            "",
            "#### Evidence",
            *([f"- {item}" for item in finding.evidence] or ["- No evidence artifact recorded."]),
            "",
            "#### Suggested remediation",
            finding.remediation or "Remediation guidance requires analyst completion.",
            "",
            f"**Discovery engine:** {finding.discovered_by}  ",
            f"**Independent validator:** {finding.validated_by or 'N/A'}  ",
            "",
        ]

    lines += [
        "## Testing constraints",
        "",
        f"- Maximum configured request rate: {campaign.target.rules.max_requests_per_second} requests/second",
        f"- Destructive testing: {'allowed' if campaign.target.rules.destructive_testing else 'prohibited'}",
        f"- Denial of service: {'allowed' if campaign.target.rules.denial_of_service else 'prohibited'}",
        f"- Social engineering: {'allowed' if campaign.target.rules.social_engineering else 'prohibited'}",
        f"- Credential attacks: {'allowed' if campaign.target.rules.credential_attacks else 'prohibited'}",
        "",
        "## Methodology note",
        "",
        "Automated discovery is separated from independent validation. Only findings marked confirmed are included as submission candidates.",
    ]
    return "\n".join(lines)
