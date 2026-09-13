from app.pentagi_status_poller import (
    PentagiPollResult,
    PentagiStatusPollError,
    poll_pentagi_flow_until_terminal,
)
from app.pentagi_status_tracker import PentagiStatusSnapshot


class _Clock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


def _snapshot(status):
    return PentagiStatusSnapshot(
        campaign_id="campaign-1",
        flow_id="flow-42",
        status=status,
        artifact={"id": f"status-{status}"},
    )


def test_poller_stops_on_finished(monkeypatch):
    statuses = iter(["created", "running", "finished"])
    monkeypatch.setattr(
        "app.pentagi_status_poller.refresh_pentagi_flow_status",
        lambda *args, **kwargs: _snapshot(next(statuses)),
    )
    clock = _Clock()
    monkeypatch.setenv("XBOW_PENTAGI_STATUS_POLL_SECONDS", "2")
    monkeypatch.setenv("XBOW_PENTAGI_STATUS_MAX_SECONDS", "30")

    result = poll_pentagi_flow_until_terminal(
        object(),
        "campaign-1",
        "receipt-1",
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
    )

    assert result == PentagiPollResult(
        flow_id="flow-42",
        status="finished",
        polls=3,
        terminal=True,
        timed_out=False,
    )
    assert clock.sleeps == [2.0, 2.0]


def test_poller_stops_on_failed(monkeypatch):
    monkeypatch.setattr(
        "app.pentagi_status_poller.refresh_pentagi_flow_status",
        lambda *args, **kwargs: _snapshot("failed"),
    )
    clock = _Clock()

    result = poll_pentagi_flow_until_terminal(
        object(),
        "campaign-1",
        "receipt-1",
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
    )

    assert result.terminal is True
    assert result.status == "failed"
    assert result.polls == 1
    assert clock.sleeps == []


def test_poller_times_out_without_infinite_loop(monkeypatch):
    monkeypatch.setattr(
        "app.pentagi_status_poller.refresh_pentagi_flow_status",
        lambda *args, **kwargs: _snapshot("running"),
    )
    clock = _Clock()
    monkeypatch.setenv("XBOW_PENTAGI_STATUS_POLL_SECONDS", "2")
    monkeypatch.setenv("XBOW_PENTAGI_STATUS_MAX_SECONDS", "5")

    result = poll_pentagi_flow_until_terminal(
        object(),
        "campaign-1",
        "receipt-1",
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
    )

    assert result.terminal is False
    assert result.timed_out is True
    assert result.status == "running"
    assert result.polls == 3
    assert sum(clock.sleeps) == 5.0


def test_poller_rejects_invalid_interval(monkeypatch):
    monkeypatch.setenv("XBOW_PENTAGI_STATUS_POLL_SECONDS", "0")
    try:
        poll_pentagi_flow_until_terminal(
            object(),
            "campaign-1",
            "receipt-1",
        )
    except PentagiStatusPollError as exc:
        assert "interval" in str(exc)
    else:
        raise AssertionError("invalid interval must fail closed")
