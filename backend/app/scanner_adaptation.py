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


_MAX_WORKER_COUNTER = 1_000_000


def _validated_worker_counters(
    raw: Any,
) -> tuple[int, int, int] | None:
    """Treat only bounded integer worker counts as trusted diagnostics."""
    if not isinstance(raw, dict):
        return None
    result = []
    for key in ("completed", "requeued", "failed"):
        value = raw.get(key, 0)
        if type(value) is not int or not 0 <= value <= _MAX_WORKER_COUNTER:
            return None
        result.append(value)
    return result[0], result[1], result[2]


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
    if worker_outcomes is None or worker_outcomes == {}:
        by_kind: dict[str, Any] = {}
        invalid_structure = False
    elif not isinstance(worker_outcomes, dict):
        by_kind = {}
        invalid_structure = True
    else:
        raw_by_kind = worker_outcomes.get("by_job_kind")
        invalid_structure = (
            "by_job_kind" in worker_outcomes
            and not isinstance(raw_by_kind, dict)
        )
        by_kind = raw_by_kind if isinstance(raw_by_kind, dict) else {}
    reasons: dict[str, str] = {}
    suppressed: set[str] = set()
    completed_by_engine: dict[str, int] = {}

    for engine in configured_engines:
        technique = memory.get(engine)
        job_kind = f"{engine}_scan"
        outcome = by_kind.get(job_kind)
        if invalid_structure or (job_kind in by_kind and not isinstance(outcome, dict)):
            reasons[engine] = "invalid worker outcome structure requires operator review"
            completed_by_engine[engine] = -1
            continue
        if outcome is None:
            completed = requeued = failed = 0
        else:
            validated = _validated_worker_counters(outcome)
            if validated is None:
                # Corrupt feedback cannot suppress a scanner or fabricate
                # a positive run for coverage rotation.
                reasons[engine] = "invalid worker outcome counters require operator review"
                completed_by_engine[engine] = -1
                continue
            completed, requeued, failed = validated
        completed_by_engine[engine] = completed

        # Technique-level "failure" may mean a valid negative security
        # result, not a scanner crash. Never suppress a configured engine
        # solely because it found no vulnerability.
        # A requeued job is not a terminal failure. Pending retries must
        # not suppress an otherwise configured scanner, even if repeated.
        unstable_worker = failed >= 2 and completed == 0
        if unstable_worker:
            reasons[engine] = (
                "worker outcomes show repeated unstable execution (terminal failures)"
            )
            suppressed.add(engine)
        elif requeued and completed == 0:
            reasons[engine] = (
                "scanner jobs are pending retry; no terminal failure "
                "threshold established"
            )
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
        if not valid_counters:
            # Do not reorder on partial or malformed operational feedback.
            return (0, 0.0, 0.0, 0, configured_order[engine])
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
