from __future__ import annotations

from typing import Any


def offensive_expansion_catalog() -> dict[str, Any]:
    """Describe requested expansion capabilities without granting execution authority."""

    return {
        "schema": "offensive-expansion-catalog-v1",
        "execution_authority": "unchanged",
        "capabilities": [
            {
                "id": "recon.subfinder",
                "status": "integrated_gated",
                "mode": "scope_bound",
                "notes": "Existing external recon runtime.",
            },
            {
                "id": "scanner.nuclei",
                "status": "integrated_gated",
                "mode": "sandboxed",
                "notes": "Existing reviewed active scanner path.",
            },
            {
                "id": "recon.amass",
                "status": "planned",
                "mode": "preview_only",
                "notes": "Not installed or executable by this catalog.",
            },
            {
                "id": "api.openapi_test_generation",
                "status": "integrated",
                "mode": "read_only_preview",
                "notes": "Built-in bounded OpenAPI/Swagger case generation.",
            },
            {
                "id": "api.security_reasoning",
                "status": "advisory",
                "mode": "read_only",
                "notes": "Prioritization remains evidence- and scope-bound.",
            },
            {
                "id": "fuzz.ffuf",
                "status": "planned",
                "mode": "preview_only",
                "notes": "No automatic fuzz execution is enabled.",
            },
            {
                "id": "fuzz.wfuzz",
                "status": "planned",
                "mode": "preview_only",
                "notes": "No automatic fuzz execution is enabled.",
            },
            {
                "id": "validation.sqlmap",
                "status": "planned",
                "mode": "preview_only",
                "notes": "No exploit/validation command dispatch is enabled.",
            },
            {
                "id": "validation.metasploit",
                "status": "planned",
                "mode": "preview_only",
                "notes": "No exploit/validation command dispatch is enabled.",
            },
            {
                "id": "reasoning.ai_prioritization",
                "status": "integrated",
                "mode": "advisory",
                "notes": "Existing adaptive planning and decision layers.",
            },
            {
                "id": "reporting.contextual_generation",
                "status": "integrated",
                "mode": "human_review_required",
                "notes": "Existing evidence-backed report generation path.",
            },
            {
                "id": "correlation.knowledge_graph",
                "status": "integrated",
                "mode": "embedded_observation_graph",
                "notes": "ObservationGraph already links assets, endpoints, findings, evidence and validation.",
            },
            {
                "id": "orchestration.workflows",
                "status": "integrated",
                "mode": "bounded_fail_closed",
                "notes": "Existing recon -> scan -> validate -> report orchestration.",
            },
        ],
    }
