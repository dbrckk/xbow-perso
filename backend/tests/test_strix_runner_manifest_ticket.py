import pytest

from app.strix_runner_manifest_ticket import (
    STRIX_RUNNER_MANIFEST_TICKET_SCHEMA,
    StrixRunnerManifestTicketError,
    build_strix_runner_manifest_ticket,
    verify_strix_runner_manifest_ticket,
)


SECRET = "fixture-manifest-ticket-secret-at-least-32-bytes"


def _descriptor(**overrides):
    values = {
        "schema": "strix-manifest-admission-v1",
        "contract_hash": "a" * 64,
        "request_id": "req-create-1",
        "image": "ghcr.io/example/sandbox@sha256:" + "b" * 64,
        "exposed_ports": [48080],
        "manifest_digest": "c" * 64,
        "entry_count": 2,
        "inline_file_count": 1,
        "local_dir_count": 1,
        "inline_file_bytes": 1024,
        "environment_value_bytes": 128,
        "host_paths_included": False,
        "raw_file_content_included": False,
        "filesystem_io_performed": False,
        "manifest_materialized": False,
        "upload_enabled": False,
        "active_execution_enabled": False,
    }
    values.update(overrides)
    return values


def test_manifest_ticket_binds_create_request_without_enabling_execution():
    ticket = build_strix_runner_manifest_ticket(
        _descriptor(),
        signing_secret=SECRET,
    )

    assert ticket.schema == STRIX_RUNNER_MANIFEST_TICKET_SCHEMA
    assert ticket.manifest_schema == "strix-manifest-admission-v1"
    assert ticket.exposed_ports == (48080,)
    assert ticket.manifest_materialized is False
    assert ticket.upload_enabled is False
    assert ticket.active_execution_enabled is False

    verified = verify_strix_runner_manifest_ticket(
        ticket.to_dict(),
        request_id="req-create-1",
        image="ghcr.io/example/sandbox@sha256:" + "b" * 64,
        exposed_ports=[48080],
        manifest_digest="c" * 64,
        verification_secret=SECRET,
    )

    assert verified.signature == ticket.signature
    assert verified.contract_hash == "a" * 64


def test_manifest_ticket_rejects_tampering():
    ticket = build_strix_runner_manifest_ticket(
        _descriptor(),
        signing_secret=SECRET,
    ).to_dict()
    ticket["entry_count"] = 3
    ticket["local_dir_count"] = 2

    with pytest.raises(
        StrixRunnerManifestTicketError,
        match="signature mismatch",
    ):
        verify_strix_runner_manifest_ticket(
            ticket,
            request_id="req-create-1",
            image="ghcr.io/example/sandbox@sha256:" + "b" * 64,
            exposed_ports=[48080],
            manifest_digest="c" * 64,
            verification_secret=SECRET,
        )


def test_manifest_ticket_rejects_request_digest_mismatch():
    ticket = build_strix_runner_manifest_ticket(
        _descriptor(),
        signing_secret=SECRET,
    )

    with pytest.raises(
        StrixRunnerManifestTicketError,
        match="does not match create request",
    ):
        verify_strix_runner_manifest_ticket(
            ticket.to_dict(),
            request_id="req-create-1",
            image=ticket.image,
            exposed_ports=[48080],
            manifest_digest="d" * 64,
            verification_secret=SECRET,
        )


@pytest.mark.parametrize(
    "field",
    (
        "host_paths_included",
        "raw_file_content_included",
        "filesystem_io_performed",
        "manifest_materialized",
        "upload_enabled",
        "active_execution_enabled",
    ),
)
def test_manifest_ticket_rejects_unsafe_invariant(field):
    with pytest.raises(
        StrixRunnerManifestTicketError,
        match="safety invariants changed",
    ):
        build_strix_runner_manifest_ticket(
            _descriptor(**{field: True}),
            signing_secret=SECRET,
        )


def test_manifest_ticket_rejects_inconsistent_counts():
    with pytest.raises(
        StrixRunnerManifestTicketError,
        match="entry counts are inconsistent",
    ):
        build_strix_runner_manifest_ticket(
            _descriptor(entry_count=3),
            signing_secret=SECRET,
        )


def test_manifest_ticket_rejects_oversized_manifest_summary():
    with pytest.raises(
        StrixRunnerManifestTicketError,
        match="inline_file_bytes is invalid",
    ):
        build_strix_runner_manifest_ticket(
            _descriptor(inline_file_bytes=4 * 1024 * 1024 + 1),
            signing_secret=SECRET,
        )


def test_manifest_ticket_requires_strong_secret():
    with pytest.raises(
        StrixRunnerManifestTicketError,
        match="at least 32 bytes",
    ):
        build_strix_runner_manifest_ticket(
            _descriptor(),
            signing_secret="short",
        )


def test_manifest_ticket_rejects_extra_fields():
    ticket = build_strix_runner_manifest_ticket(
        _descriptor(),
        signing_secret=SECRET,
    ).to_dict()
    ticket["unexpected"] = True

    with pytest.raises(
        StrixRunnerManifestTicketError,
        match="shape is invalid",
    ):
        verify_strix_runner_manifest_ticket(
            ticket,
            request_id="req-create-1",
            image="ghcr.io/example/sandbox@sha256:" + "b" * 64,
            exposed_ports=[48080],
            manifest_digest="c" * 64,
            verification_secret=SECRET,
        )
