import json

from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput
from app.observation_graph import load_observation_graph
from app.scanner_ingestion import ingest_scanner_run
from app.storage import Storage


def _campaign():
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
            ),
        ),
    )


def test_generic_scanner_ingestion_persists_chain_and_queues_validation(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    run = tmp_path / "run"
    run.mkdir()
    artifact = run / "vulnerabilities.json"
    artifact.write_text(
        json.dumps(
            {
                "vulnerabilities": [
                    {
                        "title": "Fixture issue",
                        "severity": "high",
                        "asset": "https://app.example.test",
                        "endpoint": "/profile",
                        "evidence": ["marker"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = ingest_scanner_run("strix", run, campaign, queue, store)

    assert result.engine == "strix"
    assert result.findings_seen == 1
    assert result.findings_added == 1
    assert result.validation_jobs == 1
    assert len(campaign.findings) == 1

    graph = load_observation_graph(store, campaign.id)
    assert len(graph.by_kind("asset")) == 1
    assert len(graph.by_kind("endpoint")) == 1
    assert len(graph.by_kind("finding")) == 1
    assert len(graph.by_kind("evidence")) == 1
    assert graph.by_kind("finding")[0].parent_ids == (graph.by_kind("endpoint")[0].id,)


def test_generic_scanner_ingestion_is_idempotent(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    run = tmp_path / "run"
    run.mkdir()
    artifact = run / "vulnerabilities.json"
    artifact.write_text(
        json.dumps(
            {
                "vulnerabilities": [
                    {
                        "title": "Fixture issue",
                        "severity": "medium",
                        "asset": "https://app.example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    first = ingest_scanner_run("strix", run, campaign, queue, store)
    second = ingest_scanner_run("strix", run, campaign, queue, store)

    assert first.findings_added == 1
    assert second.findings_added == 0
    assert first.validation_jobs == 1
    assert second.validation_jobs == 0
    assert len(campaign.findings) == 1
    assert queue.campaign_job_counts(campaign.id)["independent_validation"] == 1


def test_generic_scanner_ingestion_handles_missing_artifact(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    result = ingest_scanner_run("strix", tmp_path / "missing", campaign, queue, store)

    assert result.artifact_path is None
    assert result.findings_seen == 0
    assert result.findings_added == 0
    assert result.validation_jobs == 0


def test_generic_scanner_ingestion_supports_nuclei_adapter(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    run = tmp_path / "run"
    run.mkdir()
    artifact = run / "nuclei-results.jsonl"
    artifact.write_text(
        json.dumps(
            {
                "template-id": "fixture-template",
                "matched-at": "https://app.example.test/profile",
                "extracted-results": ["marker"],
                "info": {
                    "name": "Fixture issue",
                    "severity": "low",
                },
            }
        ),
        encoding="utf-8",
    )

    result = ingest_scanner_run("nuclei", run, campaign, queue, store)

    assert result.engine == "nuclei"
    assert result.findings_seen == 1
    assert result.findings_added == 1
    assert campaign.findings[0].discovered_by == "nuclei"
