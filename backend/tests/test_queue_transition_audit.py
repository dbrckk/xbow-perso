import importlib

import pytest


def _queue_audit_module():
    try:
        return importlib.import_module("app.queue_audit")
    except ModuleNotFoundError as exc:
        pytest.fail(f"queue audit contract not implemented: {exc}")


def _event(module, *, seq, from_status, to_status, previous_hash, at):
    return module.build_transition_event(
        job_id="job-1",
        campaign_id="campaign-1",
        kind="report",
        seq=seq,
        from_status=from_status,
        to_status=to_status,
        actor="worker-a" if from_status is not None else "queue",
        reason="job transitioned",
        at=at,
        previous_hash=previous_hash,
    )


def test_transition_chain_accepts_valid_lifecycle():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    second = _event(
        audit,
        seq=2,
        from_status="queued",
        to_status="running",
        previous_hash=first["event_hash"],
        at="t2",
    )
    third = _event(
        audit,
        seq=3,
        from_status="running",
        to_status="completed",
        previous_hash=second["event_hash"],
        at="t3",
    )

    result = audit.verify_transition_events([first, second, third])

    assert result == {
        "valid": True,
        "reason": None,
        "checked": 3,
        "final_status": "completed",
        "head_hash": third["event_hash"],
    }


def test_transition_chain_rejects_sequence_gap():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    forged = dict(first, seq=3)

    result = audit.verify_transition_events([first, forged])

    assert result["valid"] is False
    assert result["reason"] == "transition sequence gap"
    assert result["checked"] == 1


def test_transition_chain_rejects_status_discontinuity():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    forged = _event(
        audit,
        seq=2,
        from_status="running",
        to_status="completed",
        previous_hash=first["event_hash"],
        at="t2",
    )

    result = audit.verify_transition_events([first, forged])

    assert result["valid"] is False
    assert result["reason"] == "transition status discontinuity"
    assert result["checked"] == 1


def test_transition_chain_rejects_hash_discontinuity():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    second = _event(
        audit,
        seq=2,
        from_status="queued",
        to_status="running",
        previous_hash="0" * 64,
        at="t2",
    )

    result = audit.verify_transition_events([first, second])

    assert result["valid"] is False
    assert result["reason"] == "transition hash discontinuity"
    assert result["checked"] == 1


def test_transition_chain_rejects_event_hash_tampering():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    tampered = dict(first, actor="different-actor")

    result = audit.verify_transition_events([tampered])

    assert result["valid"] is False
    assert result["reason"] == "transition hash mismatch"
    assert result["checked"] == 0


def test_transition_builder_rejects_impossible_status_change():
    audit = _queue_audit_module()

    with pytest.raises(ValueError, match="invalid job transition"):
        _event(
            audit,
            seq=1,
            from_status="queued",
            to_status="completed",
            previous_hash=None,
            at="t1",
        )
