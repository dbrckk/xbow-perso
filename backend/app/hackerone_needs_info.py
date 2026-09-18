from __future__ import annotations

from typing import Any


def render_needs_more_info_draft(
    campaign: Any,
    request: dict[str, Any],
) -> str:
    confirmed = [
        finding
        for finding in getattr(campaign, "findings", [])
        if getattr(finding, "status", None) == "confirmed"
    ]
    lines = [
        "# HackerOne follow-up draft",
        "",
        "> **Human review required before posting to HackerOne.**",
        "",
        "## Program request",
        "",
        str(request.get("message") or "").strip(),
        "",
        "## Response draft",
        "",
        "Thanks for the follow-up. Below are the additional details currently supported by the validated local evidence.",
        "",
    ]
    if not confirmed:
        lines += [
            "No independently confirmed local finding is available yet. Add the requested information manually after validating it.",
            "",
        ]
    for index, finding in enumerate(confirmed, 1):
        lines += [
            f"### {index}. {finding.title}",
            "",
            f"- **Affected asset:** {finding.asset}",
            f"- **Endpoint:** {finding.endpoint or 'N/A'}",
            f"- **Severity:** {finding.severity.upper()}",
            f"- **Independent validator:** {finding.validated_by or 'N/A'}",
            "",
            "#### Reproduction details",
            "",
            *(
                [f"{step_index}. {step}" for step_index, step in enumerate(finding.reproduction_steps, 1)]
                or ["No reproduction steps are recorded yet."]
            ),
            "",
            "#### Evidence currently available",
            "",
            *(
                [f"- {item}" for item in finding.evidence]
                or ["- Evidence is stored in the campaign artifacts; review the exact artifact before quoting it."]
            ),
            "",
        ]
    lines += [
        "## Reviewer checklist",
        "",
        "- Answer the exact question asked by the program; do not infer missing facts.",
        "- Verify any request/response headers, payloads, timestamps, or screenshots against stored artifacts before posting.",
        "- Remove secrets, tokens, cookies, unrelated personal data, and unnecessary identifiers.",
        "- Confirm the asset remains in scope before adding new reproduction activity.",
        "- Post only after explicit human review.",
    ]
    return "\n".join(lines)
