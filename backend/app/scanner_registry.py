from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .main import Campaign, Finding
from .nuclei_parser import parse_nuclei_jsonl
from .strix_parser import parse_strix_json


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
        parser=parse_strix_json,
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



def discover_scanner_artifacts(
    engine: str,
    output_dir: str | Path,
) -> list[Path]:
    adapter = scanner_adapter(engine)
    root = Path(output_dir)
    if not root.exists() or not root.is_dir():
        return []

    try:
        root_resolved = root.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return []

    matches: dict[str, Path] = {}
    for pattern in adapter.artifact_globs:
        for candidate in root.glob(pattern):
            if candidate.is_symlink():
                continue
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root_resolved)
            except (FileNotFoundError, ValueError, OSError):
                continue
            if not resolved.is_file():
                continue
            matches[str(resolved)] = resolved

    return sorted(
        matches.values(),
        key=lambda path: (path.stat().st_mtime, str(path)),
        reverse=True,
    )


def latest_scanner_artifact(
    engine: str,
    output_dir: str | Path,
) -> Path | None:
    artifacts = discover_scanner_artifacts(engine, output_dir)
    return artifacts[0] if artifacts else None
