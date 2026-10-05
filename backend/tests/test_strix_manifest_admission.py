from pathlib import Path
from types import SimpleNamespace

import pytest

from app.strix_manifest_admission import (
    STRIX_MANIFEST_ADMISSION_SCHEMA,
    StrixManifestAdmissionError,
    build_strix_manifest_admission_plan,
)


def _file(content: bytes):
    return SimpleNamespace(type="file", content=content)


def _local_dir(path: str):
    return SimpleNamespace(type="local_dir", src=Path(path))


def _manifest(*, entries=None, environment=None, **overrides):
    values = {
        "version": 1,
        "root": "/workspace",
        "entries": dict(entries or {}),
        "environment": SimpleNamespace(value=dict(environment or {})),
        "users": [],
        "groups": [],
        "extra_path_grants": (),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_manifest_plan_admits_strix_local_dir_and_inline_file_without_raw_content():
    manifest = _manifest(
        entries={
            "repo": _local_dir("/home/user/private/repository"),
            ".strix/dependency-issues.jsonl": _file(b'{"id":"fixture"}\n'),
        },
        environment={
            "PYTHONUNBUFFERED": "1",
            "http_proxy": "http://127.0.0.1:48080",
            "NO_PROXY": "localhost,127.0.0.1",
        },
    )

    plan = build_strix_manifest_admission_plan(manifest)
    payload = plan.to_dict()
    serialized = str(payload)

    assert plan.schema == STRIX_MANIFEST_ADMISSION_SCHEMA
    assert plan.root == "/workspace"
    assert plan.entry_count == 2
    assert plan.inline_file_count == 1
    assert plan.local_dir_count == 1
    assert plan.inline_file_bytes == len(b'{"id":"fixture"}\n')
    assert plan.host_paths_included is False
    assert plan.raw_file_content_included is False
    assert plan.filesystem_io_performed is False
    assert plan.manifest_materialized is False
    assert plan.upload_enabled is False
    assert len(plan.manifest_digest) == 64
    assert "/home/user/private/repository" not in serialized
    assert '{"id":"fixture"}' not in serialized

    by_path = {item.path: item for item in plan.entries}
    local = by_path["repo"]
    assert local.kind == "local_dir"
    assert local.local_source_present is True
    assert local.local_source_path_redacted is True
    assert local.local_source_content_inspected is False
    inline = by_path[".strix/dependency-issues.jsonl"]
    assert inline.kind == "file"
    assert inline.content_bytes == len(b'{"id":"fixture"}\n')
    assert inline.content_sha256 is not None
    assert inline.content_uploaded is False


def test_manifest_digest_is_order_independent():
    first = _manifest(
        entries={
            "b.txt": _file(b"b"),
            "a.txt": _file(b"a"),
        },
        environment={"B": "2", "A": "1"},
    )
    second = _manifest(
        entries={
            "a.txt": _file(b"a"),
            "b.txt": _file(b"b"),
        },
        environment={"A": "1", "B": "2"},
    )

    left = build_strix_manifest_admission_plan(first)
    right = build_strix_manifest_admission_plan(second)

    assert left.manifest_digest == right.manifest_digest
    assert [item.path for item in left.entries] == ["a.txt", "b.txt"]
    assert [item.key for item in left.environment] == ["A", "B"]


def test_manifest_digest_changes_when_inline_file_changes():
    left = build_strix_manifest_admission_plan(
        _manifest(entries={"note.txt": _file(b"one")})
    )
    right = build_strix_manifest_admission_plan(
        _manifest(entries={"note.txt": _file(b"two")})
    )

    assert left.manifest_digest != right.manifest_digest


@pytest.mark.parametrize(
    "path",
    (
        "/absolute.txt",
        "../escape.txt",
        "nested/../escape.txt",
        "nested\\windows.txt",
        "line\nbreak.txt",
        "",
    ),
)
def test_manifest_rejects_unsafe_entry_paths(path):
    with pytest.raises(StrixManifestAdmissionError):
        build_strix_manifest_admission_plan(
            _manifest(entries={path: _file(b"x")})
        )


def test_manifest_rejects_non_path_entry_key():
    with pytest.raises(StrixManifestAdmissionError, match="text or Path"):
        build_strix_manifest_admission_plan(
            _manifest(entries={42: _file(b"x")})
        )


@pytest.mark.parametrize("kind", ("mount", "local_file", "dir", "secret"))
def test_manifest_rejects_unreviewed_entry_types(kind):
    with pytest.raises(StrixManifestAdmissionError, match="unsupported"):
        build_strix_manifest_admission_plan(
            _manifest(
                entries={
                    "entry": SimpleNamespace(type=kind),
                }
            )
        )


def test_manifest_rejects_inline_file_above_per_file_limit():
    with pytest.raises(StrixManifestAdmissionError, match="byte limit"):
        build_strix_manifest_admission_plan(
            _manifest(
                entries={
                    "large.bin": _file(b"x" * (1024 * 1024 + 1)),
                }
            )
        )


def test_manifest_rejects_total_inline_content_above_limit():
    chunk = b"x" * (1024 * 1024)
    entries = {f"{index}.bin": _file(chunk) for index in range(5)}

    with pytest.raises(StrixManifestAdmissionError, match="total byte limit"):
        build_strix_manifest_admission_plan(_manifest(entries=entries))


def test_manifest_rejects_dynamic_environment_values():
    dynamic = SimpleNamespace(value="secret-provider")

    with pytest.raises(StrixManifestAdmissionError, match="literal string"):
        build_strix_manifest_admission_plan(
            _manifest(environment={"TOKEN": dynamic})
        )


def test_manifest_environment_hides_raw_values():
    plan = build_strix_manifest_admission_plan(
        _manifest(environment={"TOKEN": "private-fixture-value"})
    )

    serialized = str(plan.to_dict())
    assert "private-fixture-value" not in serialized
    assert plan.environment[0].key == "TOKEN"
    assert plan.environment[0].value_bytes == len("private-fixture-value")
    assert len(plan.environment[0].value_sha256) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("version", 2, "version"),
        ("root", "/tmp", "root"),
        ("users", ["root"], "users"),
        ("groups", ["root"], "groups"),
        (
            "extra_path_grants",
            [SimpleNamespace(path="/tmp")],
            "extra_path_grants",
        ),
    ),
)
def test_manifest_rejects_unsupported_manifest_surface(field, value, message):
    with pytest.raises(StrixManifestAdmissionError, match=message):
        build_strix_manifest_admission_plan(
            _manifest(**{field: value})
        )


def test_manifest_local_dir_path_is_never_resolved_or_read(monkeypatch):
    source = Path("/definitely/not/present/private/repository")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("filesystem access attempted")

    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)

    plan = build_strix_manifest_admission_plan(
        _manifest(entries={"repo": SimpleNamespace(type="local_dir", src=source)})
    )

    assert plan.local_dir_count == 1
    assert plan.filesystem_io_performed is False
