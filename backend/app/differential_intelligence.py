from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .observation_graph import ObservationGraph

DifferentialSignalLevel = Literal["none", "weak", "strong"]
_SIGNAL_RANK: dict[DifferentialSignalLevel, int] = {
    "none": 0,
    "weak": 1,
    "strong": 2,
}


@dataclass(frozen=True)
class DifferentialSignal:
    finding_id: str
    signal: DifferentialSignalLevel
    parameter: str | None = None
    marker_reflected: bool = False
    status_changed: bool = False
    body_changed: bool = False
    baseline_status: int | None = None
    marker_status: int | None = None
    observation_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["observation_ids"] = list(self.observation_ids)
        return payload


def classify_differential_signal(differential: dict[str, Any] | None) -> DifferentialSignalLevel:
    """Classify read-only differential evidence without asserting exploitability."""
    if not differential or differential.get("eligible") is not True:
        return "none"
    if differential.get("reason"):
        return "none"
    if differential.get("marker_reflected") is True:
        return "strong"
    if differential.get("status_changed") is True or differential.get("body_changed") is True:
        return "weak"
    return "none"


def differential_signal_metadata(differential: dict[str, Any] | None) -> dict[str, object]:
    """Return sanitized graph metadata for a differential observation."""
    if differential is None:
        return {}
    signal = classify_differential_signal(differential)
    metadata: dict[str, object] = {
        "differential_signal": signal,
        "differential_marker_reflected": differential.get("marker_reflected") is True,
        "differential_status_changed": differential.get("status_changed") is True,
        "differential_body_changed": differential.get("body_changed") is True,
    }
    parameter = differential.get("parameter")
    if isinstance(parameter, str) and parameter:
        metadata["differential_parameter"] = parameter
    for source_key, target_key in (
        ("baseline_status", "differential_baseline_status"),
        ("marker_status", "differential_marker_status"),
    ):
        value = differential.get(source_key)
        if isinstance(value, int) and not isinstance(value, bool):
            metadata[target_key] = value
    reason = differential.get("reason")
    if isinstance(reason, str) and reason:
        metadata["differential_reason"] = reason
    return metadata


def _finding_id_from_validation(observation) -> str | None:
    value = observation.metadata.get("finding_id")
    if isinstance(value, str) and value:
        return value
    for parent_id in observation.parent_ids:
        if parent_id.startswith("finding:"):
            return parent_id[len("finding:") :]
    return None


def _signal_from_metadata(finding_id: str, observation) -> DifferentialSignal | None:
    raw_signal = observation.metadata.get("differential_signal")
    if raw_signal not in _SIGNAL_RANK:
        return None
    return DifferentialSignal(
        finding_id=finding_id,
        signal=raw_signal,
        parameter=(
            str(observation.metadata["differential_parameter"])
            if observation.metadata.get("differential_parameter")
            else None
        ),
        marker_reflected=observation.metadata.get("differential_marker_reflected") is True,
        status_changed=observation.metadata.get("differential_status_changed") is True,
        body_changed=observation.metadata.get("differential_body_changed") is True,
        baseline_status=(
            observation.metadata.get("differential_baseline_status")
            if isinstance(observation.metadata.get("differential_baseline_status"), int)
            else None
        ),
        marker_status=(
            observation.metadata.get("differential_marker_status")
            if isinstance(observation.metadata.get("differential_marker_status"), int)
            else None
        ),
        observation_ids=(observation.id,),
    )


def build_differential_signals(graph: ObservationGraph) -> dict[str, DifferentialSignal]:
    """Build one conservative differential signal per graph finding.

    Multiple validation observations are deduplicated by their graph IDs. The
    strongest signal wins while all contributing differential observation IDs
    remain attached as provenance.
    """
    finding_ids: set[str] = set()
    for finding in graph.by_kind("finding"):
        finding_ids.add(finding.id[len("finding:") :] if finding.id.startswith("finding:") else finding.id)

    candidates: dict[str, list[DifferentialSignal]] = {finding_id: [] for finding_id in finding_ids}
    provenance: dict[str, set[str]] = {finding_id: set() for finding_id in finding_ids}
    for observation in graph.by_kind("validation"):
        finding_id = _finding_id_from_validation(observation)
        if not finding_id:
            continue
        finding_ids.add(finding_id)
        candidates.setdefault(finding_id, [])
        provenance.setdefault(finding_id, set())
        signal = _signal_from_metadata(finding_id, observation)
        if signal is None:
            continue
        candidates[finding_id].append(signal)
        provenance[finding_id].add(observation.id)

    result: dict[str, DifferentialSignal] = {}
    for finding_id in sorted(finding_ids):
        items = candidates.get(finding_id, [])
        if not items:
            result[finding_id] = DifferentialSignal(finding_id=finding_id, signal="none")
            continue
        selected = max(
            items,
            key=lambda item: (
                _SIGNAL_RANK[item.signal],
                item.marker_reflected,
                item.status_changed,
                item.body_changed,
                item.observation_ids[0],
            ),
        )
        result[finding_id] = DifferentialSignal(
            finding_id=finding_id,
            signal=selected.signal,
            parameter=selected.parameter,
            marker_reflected=selected.marker_reflected,
            status_changed=selected.status_changed,
            body_changed=selected.body_changed,
            baseline_status=selected.baseline_status,
            marker_status=selected.marker_status,
            observation_ids=tuple(sorted(provenance[finding_id])),
        )
    return result


def differential_signal_rank(signal: DifferentialSignalLevel | str) -> int:
    return _SIGNAL_RANK.get(signal, 0)
