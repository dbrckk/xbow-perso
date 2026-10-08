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
    coverage_rotation_applied: bool = False
    no_completed_run_engines: tuple[str, ...] = ()
    advisory_only: bool = True
    may_expand_configuration: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["configured_engines"] = list(self.configured_engines)
        payload["selected_engines"] = list(self.selected_engines)
        payload["suppressed_engines"] = list(self.suppressed_engines)
        payload["ranked_engines"] = list(self.ranked_engines)
        payload["no_completed_run_engines"] = list(self.no_completed_run_engines)
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
    completed_by_engine: dict[str, int] = {}

    for engine in configured_engines:
        technique = memory.get(engine)
        job_kind = f"{engine}_scan"
        outcome = by_kind.get(job_kind) if isinstance(by_kind, dict) else None
        if isinstance(outcome, dict):
            try:
                completed = int(outcome.get("completed") or 0)
                requeued = int(outcome.get("requeued") or 0)
                failed = int(outcome.get("failed") or 0)
                if min(completed, requeued, failed) < 0:
                    raise ValueError("negative outcome count")
            except (TypeError, ValueError):
                # Untrusted or corrupt counters cannot justify suppressing
                # an engine or boosting a coverage recommendation.
                reasons[engine] = "invalid worker outcome counters require operator review"
                completed_by_engine[engine] = -1
                continue
        else:
            completed = requeued = failed = 0
        completed_by_engine[engine] = completed

        # Technique-level "failure" may mean a valid negative security
        # result, not a scanner crash. Never suppress a configured engine
        # solely because it found no vulnerability.
        unstable_worker = (requeued + failed) >= 2 and completed == 0
        if unstable_worker:
            reasons[engine] = (
                "worker outcomes show repeated unstable execution"
            )
            suppressed.add(engine)
        elif (
            technique
            and technique.failures >= 2
            and technique.successes == 0
        ):
            reasons[engine] = (
                "negative technique outcomes do not prove scanner failure; "
                "engine remains configured"
            )

    # Memory can reduce the configured set, but never eliminate all configured scanners.
    if suppressed == set(configured_engines):
        suppressed.clear()
        reasons = {
            engine: "suppression withheld because at least one configured scanner must remain"
            for engine in configured_engines
        }

    configured_order = {
        engine: index for index, engine in enumerate(configured_engines)
    }
    healthy = tuple(engine for engine in configured_engines if engine not in suppressed)
    valid_counters = all(completed_by_engine[engine] >= 0 for engine in healthy)
    positive_memory = any(
        memory.get(engine) is not None and memory[engine].successes > 0
        for engine in healthy
    )
    rotation = bool(
        len(healthy) > 1
        and valid_counters
        and not positive_memory
        and any(completed_by_engine[engine] >= 2 for engine in healthy)
        and any(completed_by_engine[engine] == 0 for engine in healthy)
    )
    no_completed = tuple(
        engine
        for engine in healthy
        if completed_by_engine[engine] == 0
    ) if rotation else ()
    for engine in no_completed:
        explanation = (
            "no completed worker run recorded; prefer configured scanner "
            "diversity after repeated negative scans"
        )
        reasons[engine] = (
            f"{reasons[engine]}; {explanation}"
            if engine in reasons
            else explanation
        )

    def rank_key(engine: str) -> tuple[int, float, float, int, int]:
        rotation_rank = (
            0 if engine in no_completed else 1
        ) if rotation else 0
        item = memory.get(engine)
        if item is None or item.successes <= 0:
            # Confidence in negative results is not scanner quality.
            # Preserve operator-specified order when positive outcomes
            # cannot reliably distinguish configured engines.
            return (rotation_rank, 0.0, 0.0, 0, configured_order[engine])
        return (
            rotation_rank,
            -item.confidence,
            -item.success_rate,
            -item.successes,
            configured_order[engine],
        )

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
        coverage_rotation_applied=rotation,
        no_completed_run_engines=no_completed,
    )
