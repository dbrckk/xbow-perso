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

    def note_generation(self, generation: int) -> None:
        if self.last_generation is not None and generation != self.last_generation:
            self.leadership_changes += 1
        self.last_generation = generation

    def circuit_open(self, now: datetime | None = None) -> bool:
        if not self.circuit_open_until:
            return False
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return datetime.fromisoformat(self.circuit_open_until) > current

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
            "contains_targets": False,
            "contains_payloads": False,
            "contains_secrets": False,
        }
