from app.jobqueue import JobQueue
from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.observation_graph import Observation
from app.orchestrator import advance_campaign
from app.storage import Storage


def _campaign() -> Campaign:
    return Campaign(
        id="repeat-diff",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            Finding(
                id="f1",
                title="Unknown behavioral candidate",
                severity="critical",
                asset="https://example.test",
                endpoint="https://example.test/search?q=value",
                summary="fixture",
                status="validation_required",
                discovered_by="scanner-a",
            )
        ],
    )


def _seed_graph(
    store: Storage,
    campaign: Campaign,
    *,
    signals=("strong",),
) -> None:
    store.put_observation(
        campaign.id,
        Observation(
            "asset:a",
            "asset",
            "example.test",
            "scanner-a",
        ).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        ).to_dict(),
    )
    for index, signal in enumerate(signals, start=1):
        validation_id = f"validation:{index}"
        store.put_observation(
            campaign.id,
            Observation(
                validation_id,
                "validation",
                "observed",
                f"validator-{index}",
                parent_ids=("finding:f1",),
                metadata={
                    "finding_id": "f1",
                    "differential_signal": signal,
                    "differential_parameter": "q",
                    "differential_marker_reflected": signal == "strong",
                    "differential_status_changed": False,
                    "differential_body_changed": signal != "none",
                },
            ).to_dict(),
        )
        store.put_observation(
            campaign.id,
            Observation(
                f"evidence:{index}",
                "evidence",
                "artifact-reference",
                f"validator-{index}",
                parent_ids=(validation_id,),
                metadata={
                    "artifact_id": f"artifact-{index}",
                    "artifact_kind": "validation",
                    "artifact_sha256": str(index) * 64,
                },
            ).to_dict(),
        )


def test_repeat_gate_off_preserves_explicit_resolution_stop(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    _seed_graph(store, campaign)
    monkeypatch.delenv(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION",
        raising=False,
    )

    result = advance_campaign(campaign, queue, store)

    assert result["action"]["kind"] == "stop"
    assert "explicit confirmation or rejection" in result["action"]["reason"]
    assert result["job_ids"] == []


def test_repeat_gate_queues_one_distinct_bounded_validation(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    _seed_graph(store, campaign)
    monkeypatch.setenv(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION",
        "true",
    )

    result = advance_campaign(campaign, queue, store)

    assert result["action"]["kind"] == "validate"
    assert result["action"]["reason"] == (
        "bounded repeat differential validation required"
    )
    assert len(result["job_ids"]) == 1
    job = queue.get(result["job_ids"][0])
    assert job is not None
    assert job["kind"] == "independent_validation"
    assert job["dedupe_key"] == "validation:f1:repeat:2"
    repeat = job["payload"]["repeat_validation"]
    assert repeat["schema"] == "repeat-differential-validation-v1"
    assert repeat["ordinal"] == 2
    assert repeat["reason"] == (
        "single_strong_unknown_differential_requires_repeat"
    )


def test_repeat_job_is_idempotent_for_same_graph(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    _seed_graph(store, campaign)
    monkeypatch.setenv(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION",
        "true",
    )

    first = advance_campaign(campaign, queue, store)
    second = advance_campaign(campaign, queue, store)

    assert second["job_ids"] == first["job_ids"]
    assert queue.stats()["total"] == 1


def test_second_observation_exhausts_automatic_repeat_budget(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    _seed_graph(store, campaign, signals=("strong", "weak"))
    monkeypatch.setenv(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION",
        "true",
    )

    result = advance_campaign(campaign, queue, store)

    assert result["action"]["kind"] == "stop"
    assert "explicit confirmation or rejection" in result["action"]["reason"]
    assert result["job_ids"] == []
    assert queue.stats()["total"] == 0


def test_invalid_repeat_gate_fails_closed_without_queueing(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    _seed_graph(store, campaign)
    monkeypatch.setenv(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION",
        "invalid",
    )

    result = advance_campaign(campaign, queue, store)

    assert result["action"]["kind"] == "stop"
    assert result["action"]["reason"] == (
        "invalid repeat differential validation configuration"
    )
    assert result["job_ids"] == []
    assert queue.stats()["total"] == 0
