from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_proxies_redacted_backend_diagnostics():
    nginx = _text("frontend/nginx.conf")

    for route in ("/auth-status", "/live", "/ready", "/health"):
        assert f"location {route}" in nginx
        assert f"proxy_pass http://backend:8000{route};" in nginx


def test_diagnostic_routes_bypass_service_worker_cache():
    sw = _text("frontend/sw.js")

    assert "/auth-status" in sw
    assert "/live" in sw
    assert "/ready" in sw
    assert "/health" in sw
    assert "fetch(event.request)" in sw


def test_frontend_assets_are_explicitly_cache_busted():
    index = _text("frontend/index.html")
    sw = _text("frontend/sw.js")

    assert '/app.js?v=57' in index
    assert '/hackerone.js?v=57' in index
    assert '/app.css?v=57' in index
    assert "xbow-perso-v57" in sw
