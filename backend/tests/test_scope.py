from app.main import is_host_allowed


def test_exact_host_allowed():
    assert is_host_allowed("app.example.com", ["app.example.com"], [])


def test_wildcard_subdomain_allowed():
    assert is_host_allowed("api.example.com", ["*.example.com"], [])


def test_unlisted_host_denied():
    assert not is_host_allowed("evil.example.net", ["*.example.com"], [])


def test_deny_overrides_allow():
    assert not is_host_allowed("admin.example.com", ["*.example.com"], ["admin.example.com"])
