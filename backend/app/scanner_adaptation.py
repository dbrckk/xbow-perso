from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .learning_memory import TechniqueMemory

_ALLOWED_ENGINES = {"strix", "nuclei"}


@dataclass(frozen=True)
class ScannerAdaptation:
    configured_engines: tuple[str, ...]
    selected_engines: tuple[str, ...]
    suppressed_engines: tuple[str, ...]
    ranked_engines: tuple[str, ...]
    reasons: dict[str, str]
    advisory_only: bool = True
    may_expand_configuration: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["configured_engines"] = list(self.configured_engines)
        payload["selected_engines"] = list(self.selected_engines)
        payload["suppressed_engines"] = list(self.suppressed_engines)
        payload["ranked_engines"] = list(self.ranked_engines)
        return payload


def _engine_memory(memories: Iterable[TechniqueMemory]) -> dict[str, TechniqueMemory]:
    result: dict[str, TechniqueMemory] = {}
    for item in memories:
        prefix = "scanner:"
        if not item.technique.startswith(prefix):
            continue
        engine = item.technique[len(prefix):].strip().lower()
        if engine in _ALLOWED_ENGINES:
            result[engine] = item
    return result


def adapt_scanner_engines(
    configured_engines: tuple[str, ...],
    memories: Iterable[TechniqueMemory],
    worker_outcomes: dict[str, Any] | None = None,
) -> ScannerAdaptation:
    if not configured_engines:
        raise ValueError("at least one configured scanner engine is required")
    if len(set(configured_engines)) != len(configured_engines):
        raise ValueError("configured scanner engines must be unique")
    unknown = [engine for engine in configured_engines if engine not in _ALLOWED_ENGINES]
    if unknown:
        raise ValueError(f"unsupported configured scanner engine: {unknown[0]}")

    memory = _engine_memory(memories)
    by_kind = (worker_outcomes or {}).get("by_job_kind") or {}
    reasons: dict[str, str] = {}
    suppressed: set[str] = set()

    for engine in configured_engines:
        technique = memory.get(engine)
        job_kind = f"{engine}_scan"
        outcome = by_kind.get(job_kind) if isinstance(by_kind, dict) else None
        completed = int((outcome or {}).get("completed") or 0) if isinstance(outcome, dict) else 0
        requeued = int((outcome or {}).get("requeued") or 0) if isinstance(outcome, dict) else 0
        failed = int((outcome or {}).get("failed") or 0) if isinstance(outcome, dict) else 0

        strong_memory_failure = bool(
            technique
            and technique.failures >= 2
            and technique.successes == 0
            and technique.confidence >= 0.4
        )
        unstable_worker = (requeued + failed) >= 2 and completed == 0

        if strong_memory_failure or unstable_worker:
            reason_parts = []
            if strong_memory_failure:
                reason_parts.append("evidence memory shows repeated scanner failures")
            if unstable_worker:
                reason_parts.append("worker outcomes show repeated unstable execution")
            reasons[engine] = "; ".join(reason_parts)
            suppressed.add(engine)

    # Memory can reduce the configured set, but never eliminate all configured scanners.
    if suppressed == set(configured_engines):
        suppressed.clear()
        reasons = {
            engine: "suppression withheld because at least one configured scanner must remain"
            for engine in configured_engines
        }

    def rank_key(engine: str) -> tuple[float, float, int, str]:
        item = memory.get(engine)
        if item is None:
            return (0.0, 0.0, 0, engine)
        return (-item.confidence, -item.success_rate, -item.successes, engine)

    selected = tuple(
        engine
        for engine in sorted(configured_engines, key=rank_key)
        if engine not in suppressed
    )
    return ScannerAdaptation(
        configured_engines=configured_engines,
        selected_engines=selected,
        suppressed_engines=tuple(sorted(suppressed)),
        ranked_engines=tuple(sorted(configured_engines, key=rank_key)),
        reasons=reasons,
    )
