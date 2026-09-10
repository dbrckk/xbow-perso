from __future__ import annotations

from typing import Any


def observed_independent_finding_ids(graph: Any) -> set[str]:
    """Return finding observation IDs backed by independent observed validation."""
    finding_by_id = {item.id: item for item in graph.by_kind("finding")}
    return {
        parent_id
        for validation in graph.by_kind("validation")
        if validation.value == "observed"
        for parent_id in validation.parent_ids
        if parent_id in finding_by_id and validation.source != finding_by_id[parent_id].source
    }


def attempted_finding_ids(graph: Any) -> set[str]:
    """Return finding observation IDs that have any validation attempt."""
    finding_ids = {item.id for item in graph.by_kind("finding")}
    return {
        parent_id
        for validation in graph.by_kind("validation")
        for parent_id in validation.parent_ids
        if parent_id in finding_ids
    }


def has_observed_independent_validation(graph: Any, finding_id: str) -> bool:
    return finding_id in observed_independent_finding_ids(graph)
