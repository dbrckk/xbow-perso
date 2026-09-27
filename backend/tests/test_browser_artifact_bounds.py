import pytest

from app.browser import (
    BrowserPolicyError,
    _max_browser_rendered_bytes,
    _max_browser_screenshot_bytes,
)


def test_browser_artifact_limits_have_safe_defaults(monkeypatch):
    monkeypatch.delenv("XBOW_BROWSER_MAX_RENDERED_BYTES", raising=False)
    monkeypatch.delenv("XBOW_BROWSER_MAX_SCREENSHOT_BYTES", raising=False)

    assert _max_browser_rendered_bytes() == 2 * 1024 * 1024
    assert _max_browser_screenshot_bytes() == 8 * 1024 * 1024


def test_browser_artifact_limits_accept_bounded_configuration(monkeypatch):
    monkeypatch.setenv("XBOW_BROWSER_MAX_RENDERED_BYTES", "65536")
    monkeypatch.setenv("XBOW_BROWSER_MAX_SCREENSHOT_BYTES", "131072")

    assert _max_browser_rendered_bytes() == 65536
    assert _max_browser_screenshot_bytes() == 131072


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("XBOW_BROWSER_MAX_RENDERED_BYTES", "nope", "must be an integer"),
        ("XBOW_BROWSER_MAX_RENDERED_BYTES", "1024", "must be between"),
        ("XBOW_BROWSER_MAX_SCREENSHOT_BYTES", "1024", "must be between"),
        ("XBOW_BROWSER_MAX_SCREENSHOT_BYTES", str(64 * 1024 * 1024), "must be between"),
    ],
)
def test_browser_artifact_limits_fail_closed(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)

    getter = (
        _max_browser_rendered_bytes
        if name == "XBOW_BROWSER_MAX_RENDERED_BYTES"
        else _max_browser_screenshot_bytes
    )
    with pytest.raises(BrowserPolicyError, match=message):
        getter()
