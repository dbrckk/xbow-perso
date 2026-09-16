from urllib.error import HTTPError
from urllib.request import Request

import pytest

from rehearsal_fixture import ExternalTargetAttempt, LocalRehearsalServer, MappedLoopbackOpener


def test_mapped_fixture_uses_loopback_and_preserves_fixture_host():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        with opener.open(
            Request("http://allowed.rehearsal.test/ok", method="GET"), timeout=1
        ) as response:
            assert response.getcode() == 200
        assert server.requests[-1].host.startswith("allowed.rehearsal.test")
        assert server.requests[-1].path == "/ok"
        assert opener.blocked_hosts == []


def test_unmapped_host_is_rejected_before_network_fallback():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        with pytest.raises(ExternalTargetAttempt, match="unmapped_target"):
            opener.open(
                Request("http://outside.rehearsal.test/ok", method="GET"), timeout=1
            )
        assert opener.blocked_hosts == ["outside.rehearsal.test"]
        assert server.requests == []


def test_fixture_redirect_is_not_followed():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        with pytest.raises(HTTPError) as exc:
            opener.open(
                Request(
                    "http://allowed.rehearsal.test/redirect-in-scope",
                    method="GET",
                ),
                timeout=1,
            )
        assert exc.value.code == 302
        assert [item.path for item in server.requests] == ["/redirect-in-scope"]
