from datetime import datetime, timedelta, timezone

from app.observer_resilience import ObserverHealth


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_success_resets_failure_streak():
    health = ObserverHealth(consecutive_failures=2)
    health.success(NOW)
    assert health.consecutive_failures == 0
    assert health.last_success_at == NOW.isoformat()


def test_circuit_opens_after_failure_threshold():
    health = ObserverHealth()
    health.failure(threshold=3, cooldown_seconds=60, now=NOW)
    health.failure(threshold=3, cooldown_seconds=60, now=NOW)
    assert health.circuit_open(NOW) is False
    health.failure(threshold=3, cooldown_seconds=60, now=NOW)
    assert health.circuit_open(NOW + timedelta(seconds=30)) is True
    assert health.circuit_open(NOW + timedelta(seconds=61)) is False


def test_generation_changes_are_counted():
    health = ObserverHealth()
    health.note_generation(1)
    health.note_generation(1)
    health.note_generation(2)
    assert health.leadership_changes == 1


def test_snapshot_is_redacted():
    result = ObserverHealth().snapshot()
    assert result["contains_targets"] is False
    assert result["contains_payloads"] is False
    assert result["contains_secrets"] is False
