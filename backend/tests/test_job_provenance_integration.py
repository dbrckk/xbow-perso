from types import SimpleNamespace

from app.job_provenance import verify_job_provenance
from app.jobqueue import JobQueue
from app.main import Campaign, Finding, ProgramRules, TargetInput, policy_receipt, sanitized_scan_payload
from app.observation_graph import Observation, ObservationGraph, PlannedAction
from app.orchestrator import _enqueue_action, _enqueue_recon_tasks


def _campaign(*, findings=None):
    return Campaign(
        id="campaign-provenance",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="authorization-1",
                allowed_targets=["example.test"],
                denied_targets=[],
                max_requests_per_second=2.0,
                automated_scanning=True,
            ),
        ),
        findings=findings or [],
    )


def _assert_bound(job, campaign, expected_kind):
    assert job["kind"] == expected_kind
    provenance = job["payload"]["_provenance"]
    assert provenance["schema"] == "job-provenance-v1"
    assert provenance["job_kind"] == expected_kind
    assert verify_job_provenance(job, campaign)["valid"] is True


def test_sanitized_scan_payload_is_policy_bound():
    campaign = _campaign()
    receipt = policy_receipt(campaign, "example.test", "automated_scan")

    payload = sanitized_scan_payload(campaign, receipt)

    assert payload["_provenance"]["schema"] == "job-provenance-v1"
    assert payload["_provenance"]["job_kind"] == "strix_scan"
    assert "timestamp" not in payload["policy"]
    assert "signature" not in payload["policy"]


def test_orchestrator_scan_jobs_bind_each_engine_kind(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))

    jobs = _enqueue_action(
        PlannedAction("scan", "example.test", "fixture", 80),
        campaign,
        graph,
        queue,
        scan_engines=("strix", "nuclei"),
    )

    by_kind = {job["kind"]: job for job in jobs}
    assert set(by_kind) == {"strix_scan", "nuclei_scan"}
    _assert_bound(by_kind["strix_scan"], campaign, "strix_scan")
    _assert_bound(by_kind["nuclei_scan"], campaign, "nuclei_scan")


def test_orchestrator_recon_and_browser_jobs_are_policy_bound(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_BROWSER_AUTOMATION", "true")
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    tasks = [
        SimpleNamespace(
            kind="crawl",
            target="https://example.test",
            max_requests=4,
            allowed_methods=("GET", "HEAD"),
            same_origin_only=True,
        ),
        SimpleNamespace(
            kind="browser_observe",
            target="https://example.test",
            max_requests=1,
            allowed_methods=("GET",),
            same_origin_only=True,
        ),
    ]

    jobs = _enqueue_recon_tasks(campaign, graph, queue, tasks)

    by_kind = {job["kind"]: job for job in jobs}
    assert set(by_kind) == {"recon_task", "browser_flow"}
    _assert_bound(by_kind["recon_task"], campaign, "recon_task")
    _assert_bound(by_kind["browser_flow"], campaign, "browser_flow")


def test_orchestrator_validation_and_report_jobs_are_policy_bound(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        discovered_by="scanner",
    )
    campaign = _campaign(findings=[finding])
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "candidate",
            "scanner",
            parent_ids=("a1",),
        )
    )

    validation_jobs = _enqueue_action(
        PlannedAction("validate", "example.test", "fixture", 100),
        campaign,
        graph,
        queue,
    )
    report_jobs = _enqueue_action(
        PlannedAction("report", "example.test", "fixture", 70),
        campaign,
        graph,
        queue,
    )

    assert len(validation_jobs) == 1
    assert len(report_jobs) == 1
    _assert_bound(validation_jobs[0], campaign, "independent_validation")
    _assert_bound(report_jobs[0], campaign, "report")
