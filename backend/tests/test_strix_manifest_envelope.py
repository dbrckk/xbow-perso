from __future__ import annotations

import pytest

from app.strix_manifest_envelope import (
    STRIX_MANIFEST_MAX_FILE_BYTES,
    STRIX_MANIFEST_MAX_FILES,
    StrixManifestEnvelopeError,
    build_strix_manifest_envelope,
    verify_strix_manifest_envelope,
)


def test_manifest_envelope_is_deterministic_and_content_bound():
    left = build_strix_manifest_envelope(
        {
            "notes/a.txt": "alpha",
            "config.json": b"{}",
        }
    )
    right = build_strix_manifest_envelope(
        [
            ("config.json", b"{}"),
            ("notes/a.txt", b"alpha"),
        ]
    )

    assert left == right
    assert left.file_count == 2
    assert left.total_bytes == 7
    assert left.host_paths_included is False
    assert left.file_contents_included is False
    assert left.executable_materialization_allowed is False
    assert left.materialization_enabled is False
    verify_strix_manifest_envelope(left, {"notes/a.txt": "alpha", "config.json": b"{}"})


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../escape",
        "a/../escape",
        "a//b",
        "a/./b",
        "a\\b",
        "a\nb",
    ],
)
def test_manifest_envelope_rejects_unsafe_paths(path):
    with pytest.raises(StrixManifestEnvelopeError):
        build_strix_manifest_envelope({path: b"x"})


def test_manifest_envelope_rejects_duplicate_normalized_path():
    with pytest.raises(StrixManifestEnvelopeError):
        build_strix_manifest_envelope(
            [
                ("a.txt", b"one"),
                ("a.txt", b"two"),
            ]
        )


def test_manifest_envelope_rejects_oversized_file():
    with pytest.raises(StrixManifestEnvelopeError):
        build_strix_manifest_envelope(
            {"large.bin": b"x" * (STRIX_MANIFEST_MAX_FILE_BYTES + 1)}
        )


def test_manifest_envelope_rejects_too_many_files():
    with pytest.raises(StrixManifestEnvelopeError):
        build_strix_manifest_envelope(
            [(f"f-{index}.txt", b"") for index in range(STRIX_MANIFEST_MAX_FILES + 1)]
        )


def test_manifest_verification_rejects_content_drift():
    envelope = build_strix_manifest_envelope({"a.txt": b"alpha"})
    with pytest.raises(StrixManifestEnvelopeError):
        verify_strix_manifest_envelope(envelope, {"a.txt": b"beta"})
