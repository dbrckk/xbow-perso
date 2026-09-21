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
    for route in ("/auth-status", "/live", "/ready", "/health"):
        assert route in sw
    assert "fetch(event.request)" in sw


def test_frontend_assets_are_explicitly_cache_busted():
    index = _text("frontend/index.html")
    sw = _text("frontend/sw.js")
    assert '/simple.js?v=61' in index
    assert '/app.css?v=61' in index
    assert "xbow-perso-v61" in sw


def test_api_token_is_persisted_across_browser_sessions():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert "TOKEN_KEY='xbowApiToken'" in script
    assert "localStorage.getItem(TOKEN_KEY)" in script
    assert "localStorage.setItem(TOKEN_KEY" in script
    assert "Enregistré sur cet appareil." in html


def test_frontend_has_no_totp_control():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert 'id="totp"' not in html
    assert "Code TOTP" not in html
    assert "x-totp-code" not in script



def test_simple_dashboard_runtime_is_shipped_in_frontend_image():
    dockerfile = _text("frontend/Dockerfile")
    index = _text("frontend/index.html")
    assert "COPY simple.js /usr/share/nginx/html/simple.js" in dockerfile
    assert '<script src="/simple.js?v=61" defer></script>' in index


def test_service_worker_matches_precache_assets_by_path():
    sw = _text("frontend/sw.js")
    assert "new URL(item,self.location.origin).pathname===url.pathname" in sw
