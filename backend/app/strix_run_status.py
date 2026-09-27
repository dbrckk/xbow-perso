from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StrixRunStatusError(RuntimeError):
    pass


def max_strix_run_json_bytes() -> int:
    raw = os.getenv("XBOW_MAX_STRIX_RUN_JSON_BYTES", str(256 * 1024))
    try:
        limit = int(raw)
    except ValueError as exc:
        raise StrixRunStatusError("XBOW_MAX_STRIX_RUN_JSON_BYTES must be an integer") from exc
    if not 1024 <= limit <= 2 * 1024 * 1024:
        raise StrixRunStatusError(
            "XBOW_MAX_STRIX_RUN_JSON_BYTES must be between 1 KiB and 2 MiB"
        )
    return limit


@dataclass(frozen=True)
class StrixRunStatus:
    status: str
    completed: bool
    run_json_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "completed": self.completed,
            "run_json_path": self.run_json_path,
        }


def load_strix_run_status(output_dir: str | Path) -> StrixRunStatus:
    root = Path(output_dir)
    if not root.exists() or not root.is_dir():
        raise StrixRunStatusError("Strix output directory is unavailable")

    try:
        root_resolved = root.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise StrixRunStatusError("Strix output directory is unavailable") from exc

    candidates: list[Path] = []
    for candidate in root.glob("**/run.json"):
        if candidate.is_symlink():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root_resolved)
        except (FileNotFoundError, ValueError, OSError):
            continue
        if resolved.is_file():
            candidates.append(resolved)

    if not candidates:
        raise StrixRunStatusError("Strix run.json was not produced")

    run_json = max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))
    if run_json.stat().st_size > max_strix_run_json_bytes():
        raise StrixRunStatusError("Strix run.json exceeds configured size limit")

    try:
        payload = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StrixRunStatusError("Strix run.json is unreadable or invalid") from exc
    if not isinstance(payload, dict):
        raise StrixRunStatusError("Strix run.json must contain an object")

    status = str(payload.get("status") or "").strip().lower()
    if not status:
        raise StrixRunStatusError("Strix run.json is missing status")

    return StrixRunStatus(
        status=status,
        completed=status == "completed",
        run_json_path=str(run_json),
    )
