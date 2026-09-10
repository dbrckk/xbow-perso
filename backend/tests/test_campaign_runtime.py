from datetime import datetime, timedelta, timezone

import pytest

from app.campaign_runtime import CampaignRuntimeLimit, runtime_status


def test_runtime_status_reports_remaining_budget():
    now = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    created = (now - timedelta(seconds=90)).isoformat()

    status = runtime_status(
        created,
        CampaignRuntimeLimit(max_runtime_seconds=120),
        now=now,
    )

    assert status.elapsed_seconds == 90
    assert status.remaining_seconds == 30
    assert status.exhausted is False
    assert status.reason is None


def test_runtime_status_exhausts_exactly_at_limit():
    now = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    created = (now - timedelta(seconds=120)).isoformat()

    status = runtime_status(
        created,
        CampaignRuntimeLimit(max_runtime_seconds=120),
        now=now,
    )

    assert status.remaining_seconds == 0
    assert status.exhausted is True
    assert status.reason == "campaign runtime budget exhausted"


def test_future_timestamp_never_produces_negative_elapsed():
    now = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    created = (now + timedelta(minutes=5)).isoformat()

    status = runtime_status(created, now=now)

    assert status.elapsed_seconds == 0
    assert status.exhausted is False


def test_runtime_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone"):
        runtime_status("2026-09-10T10:00:00")


def test_runtime_limit_rejects_unsafe_tiny_values():
    with pytest.raises(ValueError, match="at least 60"):
        CampaignRuntimeLimit(max_runtime_seconds=59)
