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
