import pytest

from app.scanner_sandbox import (
    ScannerSandboxConfigError,
    require_scanner_sandbox,
    safe_scanner_sandbox_admission,
    scanner_sandbox_admission,
)


_NAMES = (
    "XBOW_WORKER_ROLE",
    "XBOW_ENABLE_SCANNER_WORKER",
    "XBOW_SCANNER_SANDBOX_PROFILE",
    "XBOW_SANDBOX_READ_ONLY_ROOTFS",
    "XBOW_SANDBOX_NO_NEW_PRIVILEGES",
    "XBOW_SANDBOX_CAP_DROP_ALL",
    "XBOW_SCANNER_ALLOWED_ENGINES",
)


def _clear(monkeypatch):
    for name in _NAMES:
        monkeypatch.delenv(name, raising=False)


def _attest_runtime(monkeypatch, *, rootfs=True, nnp=True, caps=True, seccomp=True):
    monkeypatch.setattr(
        "app.scanner_sandbox._runtime_hardening_attestation",
        lambda: {
            "read_only_rootfs": rootfs,
            "no_new_privileges": nnp,
            "cap_drop_all": caps,
            "seccomp_filter": seccomp,
        },
    )


def test_scanner_sandbox_defaults_fail_closed(monkeypatch):
    _clear(monkeypatch)

    result = scanner_sandbox_admission("nuclei")

    assert result.ready is False
    assert "dedicated_scanner_worker_required" in result.block_reasons
    assert "restricted_sandbox_profile_required" in result.block_reasons
    assert "read_only_rootfs_not_attested" in result.block_reasons


def test_restricted_scanner_worker_can_admit_allowlisted_engine(monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_ROLE", "scanner")
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SANDBOX_READ_ONLY_ROOTFS", "true")
    monkeypatch.setenv("XBOW_SANDBOX_NO_NEW_PRIVILEGES", "true")
    monkeypatch.setenv("XBOW_SANDBOX_CAP_DROP_ALL", "true")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")
    _attest_runtime(monkeypatch)

    result = require_scanner_sandbox("nuclei")

    assert result.ready is True
    assert result.dedicated_worker is True
    assert result.allowed_engines == ("nuclei",)


def test_engine_must_be_explicitly_allowlisted(monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_ROLE", "scanner")
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SANDBOX_READ_ONLY_ROOTFS", "true")
    monkeypatch.setenv("XBOW_SANDBOX_NO_NEW_PRIVILEGES", "true")
    monkeypatch.setenv("XBOW_SANDBOX_CAP_DROP_ALL", "true")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")
    _attest_runtime(monkeypatch)

    with pytest.raises(ScannerSandboxConfigError, match="engine_not_allowlisted"):
        require_scanner_sandbox("strix")


def test_invalid_sandbox_boolean_fails_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_SANDBOX_CAP_DROP_ALL", "maybe")

    safe = safe_scanner_sandbox_admission("nuclei")

    assert safe["ready"] is False
    assert safe["configuration_error"] is True
    assert safe["block_reasons"] == ["invalid_sandbox_configuration"]



def test_scanner_worker_kill_switch_blocks_execution_admission(monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_ROLE", "scanner")
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "false")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SANDBOX_READ_ONLY_ROOTFS", "true")
    monkeypatch.setenv("XBOW_SANDBOX_NO_NEW_PRIVILEGES", "true")
    monkeypatch.setenv("XBOW_SANDBOX_CAP_DROP_ALL", "true")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")

    with pytest.raises(ScannerSandboxConfigError, match="scanner_worker_disabled"):
        require_scanner_sandbox("nuclei")



@pytest.mark.parametrize(
    ("rootfs", "nnp", "caps", "seccomp", "reason"),
    [
        (False, True, True, True, "runtime_rootfs_not_read_only"),
        (True, False, True, True, "runtime_no_new_privileges_missing"),
        (True, True, False, True, "runtime_capabilities_present"),
        (True, True, True, False, "runtime_seccomp_filter_missing"),
    ],
)
def test_runtime_hardening_is_verified_not_just_declared(
    monkeypatch, rootfs, nnp, caps, seccomp, reason
):
    monkeypatch.setenv("XBOW_WORKER_ROLE", "scanner")
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SANDBOX_READ_ONLY_ROOTFS", "true")
    monkeypatch.setenv("XBOW_SANDBOX_NO_NEW_PRIVILEGES", "true")
    monkeypatch.setenv("XBOW_SANDBOX_CAP_DROP_ALL", "true")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")
    _attest_runtime(monkeypatch, rootfs=rootfs, nnp=nnp, caps=caps, seccomp=seccomp)

    with pytest.raises(ScannerSandboxConfigError, match=reason):
        require_scanner_sandbox("nuclei")
