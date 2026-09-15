from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


root = Path(__file__).resolve().parents[1]

main_path = root / "backend/app/main.py"
main = main_path.read_text(encoding="utf-8")
main = replace_once(
    main,
    "from .incident_store import IncidentStore\n",
    "from .incident_store import IncidentStore\nfrom .job_provenance import attach_job_provenance\n",
    label="main provenance import",
)
main = replace_once(
    main,
    "def sanitized_scan_payload(campaign: Campaign, receipt: dict[str, Any]) -> dict[str, Any]:\n",
    "def sanitized_scan_payload(\n    campaign: Campaign,\n    receipt: dict[str, Any],\n    *,\n    job_kind: str = \"strix_scan\",\n) -> dict[str, Any]:\n",
    label="main sanitized signature",
)
main = replace_once(
    main,
    "    return {\n        \"campaign_id\": campaign.id,\n        \"target\": str(campaign.target.primary_url),\n        \"policy\": stable_receipt,\n        \"rules\": {\n            \"allowed_targets\": campaign.target.rules.allowed_targets,\n            \"denied_targets\": campaign.target.rules.denied_targets,\n            \"max_requests_per_second\": campaign.target.rules.max_requests_per_second,\n            \"destructive_testing\": False,\n            \"denial_of_service\": False,\n            \"social_engineering\": False,\n            \"credential_attacks\": False,\n            \"automated_scanning\": campaign.target.rules.automated_scanning,\n        },\n    }\n",
    "    payload = {\n        \"campaign_id\": campaign.id,\n        \"target\": str(campaign.target.primary_url),\n        \"policy\": stable_receipt,\n        \"rules\": {\n            \"allowed_targets\": campaign.target.rules.allowed_targets,\n            \"denied_targets\": campaign.target.rules.denied_targets,\n            \"max_requests_per_second\": campaign.target.rules.max_requests_per_second,\n            \"destructive_testing\": False,\n            \"denial_of_service\": False,\n            \"social_engineering\": False,\n            \"credential_attacks\": False,\n            \"automated_scanning\": campaign.target.rules.automated_scanning,\n        },\n    }\n    return attach_job_provenance(\n        payload,\n        campaign,\n        job_kind=job_kind,\n        action=\"automated_scan\",\n    )\n",
    label="main sanitized body",
)
main_path.write_text(main, encoding="utf-8")

orchestrator_path = root / "backend/app/orchestrator.py"
orch = orchestrator_path.read_text(encoding="utf-8")
orch = replace_once(
    orch,
    "from .hypothesis_memory import build_hypotheses\nfrom .jobqueue import JobQueue\n",
    "from .hypothesis_memory import build_hypotheses\nfrom .job_provenance import attach_job_provenance\nfrom .jobqueue import JobQueue\n",
    label="orchestrator provenance import",
)
orch = replace_once(
    orch,
    '''                    {\n                        "campaign_id": campaign.id,\n                        "steps": [\n                            {\n                                "operation": "navigate",\n                                "url": task.target,\n                                "timeout_ms": 10000,\n                            },\n                            {\n                                "operation": "screenshot",\n                                "timeout_ms": 10000,\n                            },\n                        ],\n                    },\n''',
    '''                    attach_job_provenance(\n                        {\n                            "campaign_id": campaign.id,\n                            "steps": [\n                                {\n                                    "operation": "navigate",\n                                    "url": task.target,\n                                    "timeout_ms": 10000,\n                                },\n                                {\n                                    "operation": "screenshot",\n                                    "timeout_ms": 10000,\n                                },\n                            ],\n                        },\n                        campaign,\n                        job_kind="browser_flow",\n                        action="crawl",\n                    ),\n''',
    label="orchestrator browser provenance",
)
orch = replace_once(
    orch,
    '''                {\n                    "campaign_id": campaign.id,\n                    "kind": task.kind,\n                    "target": task.target,\n                    "max_requests": task.max_requests,\n                    "allowed_methods": list(task.allowed_methods),\n                    "same_origin_only": task.same_origin_only,\n                },\n''',
    '''                attach_job_provenance(\n                    {\n                        "campaign_id": campaign.id,\n                        "kind": task.kind,\n                        "target": task.target,\n                        "max_requests": task.max_requests,\n                        "allowed_methods": list(task.allowed_methods),\n                        "same_origin_only": task.same_origin_only,\n                    },\n                    campaign,\n                    job_kind="recon_task",\n                    action="crawl",\n                ),\n''',
    label="orchestrator recon provenance",
)
orch = replace_once(
    orch,
    '''        payload = sanitized_scan_payload(campaign, stable_receipt)\n        jobs = []\n        engines = scan_engines if scan_engines is not None else _scan_engines()\n        for engine in engines:\n            kind = "strix_scan" if engine == "strix" else "nuclei_scan"\n            jobs.append(\n''',
    '''        jobs = []\n        engines = scan_engines if scan_engines is not None else _scan_engines()\n        for engine in engines:\n            kind = "strix_scan" if engine == "strix" else "nuclei_scan"\n            payload = sanitized_scan_payload(\n                campaign,\n                stable_receipt,\n                job_kind=kind,\n            )\n            jobs.append(\n''',
    label="orchestrator scan provenance",
)
orch = replace_once(
    orch,
    '''                    {"campaign_id": campaign.id, "finding_id": finding.id, "asset": finding.asset},\n''',
    '''                    attach_job_provenance(\n                        {"campaign_id": campaign.id, "finding_id": finding.id, "asset": finding.asset},\n                        campaign,\n                        job_kind="independent_validation",\n                        action="validate",\n                    ),\n''',
    label="orchestrator validation provenance",
)
orch = replace_once(
    orch,
    '''                {"campaign_id": campaign.id, "platform": "generic"},\n''',
    '''                attach_job_provenance(\n                    {"campaign_id": campaign.id, "platform": "generic"},\n                    campaign,\n                    job_kind="report",\n                    action="report",\n                ),\n''',
    label="orchestrator report provenance",
)
orchestrator_path.write_text(orch, encoding="utf-8")
