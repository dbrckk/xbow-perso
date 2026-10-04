import json
from pathlib import Path

import pytest

from app.strix_runner_rpc import (
    RunnerRpcError,
    RunnerSessionState,
)


ROOT = Path(__file__).resolve().parents[2]


def test_session_create_is_idempotent_by_client_request_id():
    state = RunnerSessionState(max_sessions=4)

    first = state.create_session(
        contract_hash="a" * 64,
        client_request_id="b" * 32,
    )
    second = state.create_session(
        contract_hash="a" * 64,
        client_request_id="b" * 32,
    )

    assert first == second
    assert first["schema"] == "strix-remote-session-v1"
    assert first["contract_hash"] == "a" * 64
    assert len(first["session_id"]) == 32
    assert first["capabilities"] == {
        "exec": False,
        "write": False,
        "resolve_exposed_port": False,
    }


def test_same_request_id_cannot_change_contract():
    state = RunnerSessionState(max_sessions=4)
    state.create_session(
        contract_hash="a" * 64,
        client_request_id="b" * 32,
    )

    with pytest.raises(RunnerRpcError, match="request id"):
        state.create_session(
            contract_hash="c" * 64,
            client_request_id="b" * 32,
        )


def test_session_capacity_fails_closed():
    state = RunnerSessionState(max_sessions=1)
    state.create_session(
        contract_hash="a" * 64,
        client_request_id="b" * 32,
    )

    with pytest.raises(RunnerRpcError, match="capacity"):
        state.create_session(
            contract_hash="c" * 64,
            client_request_id="d" * 32,
        )


def test_delete_is_idempotent():
    state = RunnerSessionState(max_sessions=4)
    created = state.create_session(
        contract_hash="a" * 64,
        client_request_id="b" * 32,
    )

    assert state.delete_session(created["session_id"]) is True
    assert state.delete_session(created["session_id"]) is False


@pytest.mark.parametrize(
    "operation",
    ["exec", "write", "resolve_exposed_port"],
)
def test_execution_operations_remain_disabled(operation):
    state = RunnerSessionState(max_sessions=4)
    created = state.create_session(
        contract_hash="a" * 64,
        client_request_id="b" * 32,
    )

    with pytest.raises(RunnerRpcError, match="disabled"):
        state.require_operation(created["session_id"], operation)


def test_unknown_session_is_rejected_before_operation():
    state = RunnerSessionState(max_sessions=4)

    with pytest.raises(RunnerRpcError, match="unknown session"):
        state.require_operation("a" * 32, "exec")


def test_runner_image_starts_authenticated_rpc_server():
    dockerfile = (ROOT / "backend" / "Dockerfile.strix-runner").read_text()

    assert "COPY app/strix_remote_session_protocol.py" in dockerfile
    assert "COPY app/strix_runner_rpc.py" in dockerfile
    assert (
        'CMD ["python", "-m", "app.strix_runner_rpc", "--serve"]'
        in dockerfile
    )


def test_runner_compose_exposes_only_internal_rpc_port():
    compose = (ROOT / "docker-compose.yml").read_text()
    block = compose.split("  strix-runner:", 1)[1].split(
        "\n  scanner-worker:",
        1,
    )[0]

    assert "XBOW_STRIX_RUNNER_RPC_KEY:" in block
    assert 'expose:\n      - "8092"' in block
    assert "\n    ports:" not in block
    assert "networks: [strix-broker]" in block
    assert "docker.sock" not in block
    assert "XBOW_STRIX_ACTIVE_EXECUTION: \"false\"" in block


def test_ci_probes_rpc_create_block_and_delete():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "XBOW_STRIX_RUNNER_RPC_KEY" in workflow
    assert "python -m app.strix_runner_rpc --probe" in workflow
    assert "rpc_probe_ok" in workflow


def test_state_snapshot_never_contains_request_ids():
    state = RunnerSessionState(max_sessions=4)
    state.create_session(
        contract_hash="a" * 64,
        client_request_id="b" * 32,
    )

    snapshot = state.snapshot()

    encoded = json.dumps(snapshot, sort_keys=True)
    assert "b" * 32 not in encoded
    assert snapshot["session_count"] == 1
    assert snapshot["active_execution_enabled"] is False
