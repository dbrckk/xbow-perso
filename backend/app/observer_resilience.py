from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class ObserverHealth:
    consecutive_failures: int = 0
    last_success_at: str | None = None
    last_failure_at: str | None = None
    leadership_changes: int = 0
    last_generation: int | None = None
    circuit_open_until: str | None = None
    last_cycle_duration_seconds: float | None = None
    deadline_exceeded_count: int = 0
    leadership_lost_count: int = 0

    def note_generation(self, generation: int) -> None:
        if self.last_generation is not None and generation != self.last_generation:
            self.leadership_changes += 1
        self.last_generation = generation

    def circuit_open(self, now: datetime | None = None) -> bool:
        if not self.circuit_open_until:
            return False
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return datetime.fromisoformat(self.circuit_open_until) > current

    def note_cycle_duration(self, seconds: float) -> None:
        self.last_cycle_duration_seconds = max(0.0, float(seconds))

    def note_deadline_exceeded(self) -> None:
        self.deadline_exceeded_count += 1

    def note_leadership_lost(self) -> None:
        self.leadership_lost_count += 1

    def success(self, now: datetime | None = None) -> None:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.consecutive_failures = 0
        self.last_success_at = current.isoformat()
        self.circuit_open_until = None

    def failure(
        self,
        *,
        threshold: int = 3,
        cooldown_seconds: int = 60,
        now: datetime | None = None,
    ) -> None:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.consecutive_failures += 1
        self.last_failure_at = current.isoformat()
        if self.consecutive_failures >= threshold:
            self.circuit_open_until = (
                current + timedelta(seconds=cooldown_seconds)
            ).isoformat()

    def snapshot(self) -> dict[str, Any]:
        return {
            "consecutive_failures": self.consecutive_failures,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "leadership_changes": self.leadership_changes,
            "last_generation": self.last_generation,
            "circuit_open_until": self.circuit_open_until,
            "last_cycle_duration_seconds": self.last_cycle_duration_seconds,
            "deadline_exceeded_count": self.deadline_exceeded_count,
            "leadership_lost_count": self.leadership_lost_count,
            "contains_targets": False,
            "contains_payloads": False,
            "contains_secrets": False,
        }
