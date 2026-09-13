from __future__ import annotations

import os
import time
from dataclasses import dataclass

from .pentagi_status_tracker import PentagiStatusSnapshot, refresh_pentagi_flow_status

_TERMINAL_STATUSES = {"finished", "failed"}


class PentagiStatusPollError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiPollResult:
    flow_id: str
    status: str
    polls: int
    terminal: bool
    timed_out: bool


def _poll_interval_seconds() -> float:
    raw = (os.getenv("XBOW_PENTAGI_STATUS_POLL_SECONDS") or "10").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise PentagiStatusPollError(
            "XBOW_PENTAGI_STATUS_POLL_SECONDS must be numeric"
        ) from exc
    if not 1.0 <= value <= 300.0:
        raise PentagiStatusPollError(
            "PentAGI status poll interval must be between 1 and 300 seconds"
        )
    return value


def _max_poll_seconds() -> float:
    raw = (os.getenv("XBOW_PENTAGI_STATUS_MAX_SECONDS") or "3600").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise PentagiStatusPollError(
            "XBOW_PENTAGI_STATUS_MAX_SECONDS must be numeric"
        ) from exc
    if not 5.0 <= value <= 86400.0:
        raise PentagiStatusPollError(
            "PentAGI status max duration must be between 5 seconds and 24 hours"
        )
    return value


def poll_pentagi_flow_until_terminal(
    store,
    campaign_id: str,
    receipt_artifact_id: str,
    *,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
) -> PentagiPollResult:
    """Poll one existing PentAGI flow until a terminal state or bounded timeout."""

    interval = _poll_interval_seconds()
    max_seconds = _max_poll_seconds()
    deadline = monotonic_fn() + max_seconds
    polls = 0
    last: PentagiStatusSnapshot | None = None

    while True:
        now = monotonic_fn()
        if now >= deadline:
            if last is None:
                raise PentagiStatusPollError(
                    "PentAGI status polling deadline elapsed before first refresh"
                )
            return PentagiPollResult(
                flow_id=last.flow_id,
                status=last.status,
                polls=polls,
                terminal=False,
                timed_out=True,
            )

        last = refresh_pentagi_flow_status(
            store,
            campaign_id,
            receipt_artifact_id,
        )
        polls += 1

        if last.status in _TERMINAL_STATUSES:
            return PentagiPollResult(
                flow_id=last.flow_id,
                status=last.status,
                polls=polls,
                terminal=True,
                timed_out=False,
            )

        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            return PentagiPollResult(
                flow_id=last.flow_id,
                status=last.status,
                polls=polls,
                terminal=False,
                timed_out=True,
            )
        sleep_fn(min(interval, remaining))
