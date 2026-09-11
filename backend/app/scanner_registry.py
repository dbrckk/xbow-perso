from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .main import Campaign, Finding
from .nuclei_parser import parse_nuclei_jsonl
from .worker import parse_strix_vulnerabilities


Parser = Callable[[str | Path, Campaign], list[Finding]]


@dataclass(frozen=True)
class ScannerAdapter:
    engine: str
    format: str
    parser: Parser
    artifact_globs: tuple[str, ...]


_ADAPTERS: dict[str, ScannerAdapter] = {
    "strix": ScannerAdapter(
        engine="strix",
        format="json",
        parser=parse_strix_vulnerabilities,
        artifact_globs=("**/vulnerabilities.json",),
    ),
    "nuclei": ScannerAdapter(
        engine="nuclei",
        format="jsonl",
        parser=parse_nuclei_jsonl,
        artifact_globs=("**/*.jsonl", "**/nuclei*.jsonl"),
    ),
}


def scanner_adapter(engine: str) -> ScannerAdapter:
    key = str(engine).strip().lower()
    try:
        return _ADAPTERS[key]
    except KeyError as exc:
        raise ValueError(f"unsupported scanner engine: {engine}") from exc


def scanner_adapters() -> tuple[ScannerAdapter, ...]:
    return tuple(_ADAPTERS[key] for key in sorted(_ADAPTERS))


def parse_scanner_artifact(
    engine: str,
    path: str | Path,
    campaign: Campaign,
) -> list[Finding]:
    return scanner_adapter(engine).parser(path, campaign)
