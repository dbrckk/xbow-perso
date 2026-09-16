from __future__ import annotations

import ipaddress
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ExternalTargetAttempt(RuntimeError):
    pass


@dataclass(frozen=True)
class RequestRecord:
    method: str
    host: str
    path: str


STATIC_ROUTES: dict[str, tuple[int, dict[str, str], bytes]] = {
    "/ok": (200, {}, b"ok"),
    "/redirect-in-scope": (302, {"Location": "/ok"}, b""),
    "/redirect-out-of-scope": (
        302,
        {"Location": "http://outside.rehearsal.test/ok"},
        b"",
    ),
    "/throttle": (429, {"Retry-After": "1"}, b"throttled"),
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _FixtureHandler(BaseHTTPRequestHandler):
    server_version = "XBOWRehearsal/1"
    sys_version = ""

    def do_GET(self) -> None:
        self._respond()

    def do_HEAD(self) -> None:
        self._respond(head_only=True)

    def _respond(self, *, head_only: bool = False) -> None:
        parsed = urlsplit(self.path)
        request_log = getattr(self.server, "request_log")
        request_log.append(
            RequestRecord(
                method=self.command,
                host=self.headers.get("Host", ""),
                path=parsed.path,
            )
        )

        if parsed.path in {"/echo", "/secret-echo"}:
            values = parse_qs(parsed.query, keep_blank_values=True)
            first = next((items[0] for items in values.values() if items), "")
            status, headers, body = 200, {}, first.encode("utf-8")
        else:
            status, headers, body = STATIC_ROUTES.get(
                parsed.path,
                (404, {}, b"not found"),
            )

        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only and body:
            self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


class LocalRehearsalServer:
    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.requests: list[RequestRecord] = []

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("server_not_started")
        return int(self._server.server_address[1])

    def __enter__(self) -> "LocalRehearsalServer":
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        server.daemon_threads = True
        server.request_log = self.requests
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None


class MappedLoopbackOpener:
    def __init__(self, hosts: dict[str, tuple[str, int]]) -> None:
        self._hosts: dict[str, tuple[str, int]] = {}
        self.blocked_hosts: list[str] = []
        for hostname, destination in hosts.items():
            address, port = destination
            if not ipaddress.ip_address(address).is_loopback:
                raise ValueError("mapped_target_must_be_loopback")
            if not 1 <= int(port) <= 65535:
                raise ValueError("mapped_target_port_invalid")
            self._hosts[hostname.lower().rstrip(".")] = (address, int(port))
        self._opener = build_opener(_NoRedirect())

    def open(self, request: Request | str, timeout: float | None = None):
        original = request if isinstance(request, Request) else Request(request)
        parsed = urlsplit(original.full_url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        destination = self._hosts.get(hostname)
        if destination is None:
            self.blocked_hosts.append(hostname)
            raise ExternalTargetAttempt("unmapped_target")

        address, port = destination
        if not ipaddress.ip_address(address).is_loopback:
            self.blocked_hosts.append(hostname)
            raise ExternalTargetAttempt("non_loopback_target")

        connect_host = f"[{address}]" if ":" in address else address
        rewritten = urlunsplit(
            (
                parsed.scheme,
                f"{connect_host}:{port}",
                parsed.path or "/",
                parsed.query,
                parsed.fragment,
            )
        )
        forwarded = Request(
            rewritten,
            data=original.data,
            headers=dict(original.header_items()),
            method=original.get_method(),
        )
        forwarded.add_header("Host", parsed.netloc)
        return self._opener.open(forwarded, timeout=timeout)
