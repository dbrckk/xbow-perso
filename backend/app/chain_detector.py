from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .observation_graph import ObservationGraph


@dataclass(frozen=True)
class ObservationChain:
    node_ids: tuple[str, ...]
    kinds: tuple[str, ...]
    terminal_kind: str
    complete_validation_chain: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["node_ids"] = list(self.node_ids)
        payload["kinds"] = list(self.kinds)
        return payload


def detect_chains(
    graph: ObservationGraph,
    *,
    max_depth: int = 8,
    limit: int = 50,
) -> list[ObservationChain]:
    """Return bounded provenance chains from the observation graph.

    The detector is read-only. It follows existing parent relationships and does
    not infer exploit steps, targets, payloads, or new network actions.
    """
    if not 1 <= max_depth <= 32:
        raise ValueError("max_depth must be between 1 and 32")
    if not 1 <= limit <= 200:
        raise ValueError("chain limit must be between 1 and 200")

    items = {item.id: item for item in graph.values()}
    children: dict[str, list[str]] = {item_id: [] for item_id in items}
    for item in items.values():
        for parent_id in item.parent_ids:
            if parent_id in children:
                children[parent_id].append(item.id)
    for node_ids in children.values():
        node_ids.sort()

    roots = sorted(item.id for item in items.values() if not item.parent_ids)
    chains: list[ObservationChain] = []

    def walk(path: tuple[str, ...]) -> None:
        if len(chains) >= limit:
            return
        current = path[-1]
        next_nodes = [node_id for node_id in children.get(current, ()) if node_id not in path]
        if len(path) >= max_depth or not next_nodes:
            kinds = tuple(items[node_id].kind for node_id in path)
            chains.append(
                ObservationChain(
                    node_ids=path,
                    kinds=kinds,
                    terminal_kind=kinds[-1],
                    complete_validation_chain=(
                        "finding" in kinds
                        and "validation" in kinds
                        and "evidence" in kinds
                    ),
                )
            )
            return
        for child_id in next_nodes:
            walk((*path, child_id))
            if len(chains) >= limit:
                return

    for root_id in roots:
        walk((root_id,))
        if len(chains) >= limit:
            break

    return sorted(
        chains,
        key=lambda item: (
            not item.complete_validation_chain,
            -len(item.node_ids),
            item.node_ids,
        ),
    )[:limit]
