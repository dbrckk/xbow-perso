from datetime import datetime, timedelta, timezone

from app.observer_metrics import observer_health_metrics
from app.observer_resilience import ObserverHealth


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_observer_health_metrics_exposes_redacted_ages_and_counters():
    health = ObserverHealth(
        consecutive_failures=2,
        last_success_at=(NOW - timedelta(seconds=30)).isoformat(),
        last_failure_at=(NOW - timedelta(seconds=5)).isoformat(),
        last_cycle_duration_seconds=1.25,
        leadership_changes=3,
        leadership_lost_count=2,
        deadline_exceeded_count=4,
    )
    result = observer_health_metrics(health.snapshot(), now=NOW)
    assert result["last_success_age_seconds"] == 30
    assert result["last_failure_age_seconds"] == 5
    assert result["last_cycle_duration_seconds"] == 1.25
    assert result["leadership_lost_count"] == 2
    assert result["deadline_exceeded_count"] == 4
    assert result["contains_targets"] is False


def test_health_object_tracks_new_counters():
    health = ObserverHealth()
    health.note_cycle_duration(2.5)
    health.note_deadline_exceeded()
    health.note_leadership_lost()
    result = health.snapshot()
    assert result["last_cycle_duration_seconds"] == 2.5
    assert result["deadline_exceeded_count"] == 1
    assert result["leadership_lost_count"] == 1
