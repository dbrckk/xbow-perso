from email.message import Message

from app.main import Campaign, ProgramRules, TargetInput
from app.recon_worker import execute_recon_task


class _Response:
    def __init__(self, body: bytes, headers: dict[str, str], status: int = 200):
        self._body = body
        self.status = status
        message = Message()
        for key, value in headers.items():
            message[key] = value
        self.headers = message

    def read(self, _limit: int):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Opener:
    def __init__(self, response):
        self.response = response

    def open(self, _request, timeout):
        assert timeout > 0
        return self.response


def _campaign():
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )


def test_recon_worker_is_dry_run_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_RECON", raising=False)

    result = execute_recon_task(
        _campaign(),
        {"kind": "crawl", "target": "https://example.test"},
    )

    assert result.status == "dry_run"
    assert result.endpoints == ()
    assert result.forms == ()


def test_recon_worker_extracts_only_same_origin_read_only_surface(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")
    html = b"""
    <html>
      <a href="/public">public</a>
      <a href="https://outside.test/escape">outside</a>
      <form action="/search" method="get">
        <input name="q">
      </form>
      <form action="/submit" method="post">
        <input name="secret">
      </form>
    </html>
    """
    response = _Response(html, {"Content-Type": "text/html"})
    monkeypatch.setattr(
        "app.recon_worker.build_opener",
        lambda *_args, **_kwargs: _Opener(response),
    )

    result = execute_recon_task(
        _campaign(),
        {"kind": "crawl", "target": "https://example.test"},
    )

    assert result.status == "observed"
    assert result.endpoints == ("https://example.test/public",)
    assert result.forms == (
        {
            "action": "https://example.test/search",
            "method": "GET",
            "input_names": ["q"],
        },
    )
    assert "outside.test" not in str(result)


def test_recon_worker_detects_bounded_technology_headers(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")
    response = _Response(
        b"",
        {
            "Content-Type": "text/plain",
            "Server": "fixture-server",
            "X-Powered-By": "fixture-runtime",
            "CF-Ray": "abc",
        },
    )
    monkeypatch.setattr(
        "app.recon_worker.build_opener",
        lambda *_args, **_kwargs: _Opener(response),
    )

    result = execute_recon_task(
        _campaign(),
        {"kind": "detect_technology", "target": "https://example.test"},
    )

    assert set(result.technologies) == {
        "Server:fixture-server",
        "X-Powered-By:fixture-runtime",
    }
    assert result.waf == ("CF-Ray",)


def test_recon_worker_rejects_out_of_scope_target(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")

    try:
        execute_recon_task(
            _campaign(),
            {"kind": "crawl", "target": "https://outside.test"},
        )
    except Exception as exc:
        assert "outside declared scope" in str(exc)
    else:
        raise AssertionError("out-of-scope recon must fail closed")


def test_recon_worker_enriches_same_origin_resources_without_extra_requests(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")
    html = b"""
    <html>
      <a href="/page">page</a>
      <script src="/assets/app.js"></script>
      <link rel="stylesheet" href="/assets/app.css">
      <iframe src="/frame"></iframe>
      <script src="https://outside.test/escape.js"></script>
      <script src="data:text/javascript,alert(1)"></script>
    </html>
    """
    response = _Response(html, {"Content-Type": "text/html"})
    opener = _Opener(response)
    calls = {"count": 0}

    def _open(_request, timeout):
        calls["count"] += 1
        assert timeout > 0
        return response

    opener.open = _open
    monkeypatch.setattr(
        "app.recon_worker.build_opener",
        lambda *_args, **_kwargs: opener,
    )

    result = execute_recon_task(
        _campaign(),
        {"kind": "crawl", "target": "https://example.test"},
    )

    assert calls["count"] == 1
    assert set(result.endpoints) == {
        "https://example.test/page",
        "https://example.test/assets/app.js",
        "https://example.test/assets/app.css",
        "https://example.test/frame",
    }
    assert "outside.test" not in str(result)
    assert "data:text" not in str(result)


def test_recon_surface_parser_bounds_discovered_links_and_form_inputs(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")
    links = "".join(f'<a href="/p/{index}">x</a>' for index in range(700))
    inputs = "".join(f'<input name="field-{index}">' for index in range(150))
    html = f"<html>{links}<form action='/search' method='get'>{inputs}</form></html>".encode()
    response = _Response(html, {"Content-Type": "text/html"})
    monkeypatch.setattr(
        "app.recon_worker.build_opener",
        lambda *_args, **_kwargs: _Opener(response),
    )

    result = execute_recon_task(
        _campaign(),
        {"kind": "crawl", "target": "https://example.test"},
    )

    assert len(result.endpoints) == 100
    assert len(result.forms) == 1
    assert len(result.forms[0]["input_names"]) == 100


class _RoutingOpener:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def open(self, request, timeout):
        assert timeout > 0
        url = request.full_url
        self.calls.append(url)
        return self.routes[url]


def test_recon_worker_crawls_multiple_pages_with_explicit_budget(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")
    monkeypatch.setenv("XBOW_RECON_MAX_REQUESTS", "4")
    monkeypatch.setenv("XBOW_RECON_MAX_DEPTH", "2")
    monkeypatch.setenv("XBOW_RECON_MAX_RPS", "10")
    monkeypatch.setattr("app.recon_worker.time.sleep", lambda _seconds: None)

    opener = _RoutingOpener(
        {
            "https://example.test/": _Response(
                b'<a href="/one">one</a><a href="https://outside.test/nope">outside</a>',
                {"Content-Type": "text/html"},
            ),
            "https://example.test/one": _Response(
                b'<a href="/two">two</a><form action="/search" method="get"><input name="q"></form>',
                {"Content-Type": "text/html"},
            ),
            "https://example.test/two": _Response(
                b'<a href="/three">three</a>',
                {"Content-Type": "text/html"},
            ),
            "https://example.test/three": _Response(
                b"<html></html>",
                {"Content-Type": "text/html"},
            ),
        }
    )
    monkeypatch.setattr("app.recon_worker.build_opener", lambda *_args, **_kwargs: opener)

    result = execute_recon_task(
        _campaign(),
        {
            "kind": "crawl",
            "target": "https://example.test",
            "max_requests": 4,
        },
    )

    assert opener.calls == [
        "https://example.test/",
        "https://example.test/one",
        "https://example.test/two",
    ]
    assert set(result.endpoints) == {
        "https://example.test/one",
        "https://example.test/two",
        "https://example.test/three",
    }
    assert result.forms == (
        {
            "action": "https://example.test/search",
            "method": "GET",
            "input_names": ["q"],
        },
    )
    assert "outside.test" not in str(result)


def test_recon_worker_respects_local_request_cap(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")
    monkeypatch.setenv("XBOW_RECON_MAX_REQUESTS", "2")
    monkeypatch.setenv("XBOW_RECON_MAX_DEPTH", "5")
    monkeypatch.setenv("XBOW_RECON_MAX_RPS", "10")
    monkeypatch.setattr("app.recon_worker.time.sleep", lambda _seconds: None)

    opener = _RoutingOpener(
        {
            "https://example.test/": _Response(
                b'<a href="/one">one</a>',
                {"Content-Type": "text/html"},
            ),
            "https://example.test/one": _Response(
                b'<a href="/two">two</a>',
                {"Content-Type": "text/html"},
            ),
        }
    )
    monkeypatch.setattr("app.recon_worker.build_opener", lambda *_args, **_kwargs: opener)

    result = execute_recon_task(
        _campaign(),
        {
            "kind": "crawl",
            "target": "https://example.test",
            "max_requests": 40,
        },
    )

    assert opener.calls == ["https://example.test/", "https://example.test/one"]
    assert "https://example.test/two" in result.endpoints


def test_recon_worker_rejects_invalid_request_budget(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")

    try:
        execute_recon_task(
            _campaign(),
            {
                "kind": "crawl",
                "target": "https://example.test",
                "max_requests": 0,
            },
        )
    except Exception as exc:
        assert "max_requests must be between 1 and 100" in str(exc)
    else:
        raise AssertionError("invalid crawl budget must fail closed")


def test_recon_worker_rejects_invalid_local_depth(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_RECON", "1")
    monkeypatch.setenv("XBOW_RECON_MAX_DEPTH", "99")

    try:
        execute_recon_task(
            _campaign(),
            {
                "kind": "crawl",
                "target": "https://example.test",
                "max_requests": 2,
            },
        )
    except Exception as exc:
        assert "XBOW_RECON_MAX_DEPTH" in str(exc)
    else:
        raise AssertionError("invalid crawl depth must fail closed")
