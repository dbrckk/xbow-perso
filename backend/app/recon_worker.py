from __future__ import annotations

import math
import os
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ReconPolicyError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ReconResult:
    status: str
    target: str
    endpoints: tuple[str, ...] = ()
    forms: tuple[dict, ...] = ()
    technologies: tuple[str, ...] = ()
    waf: tuple[str, ...] = ()
    http_status: int | None = None
    error: str | None = None


_MAX_DISCOVERED_LINKS = 500
_MAX_DISCOVERED_FORMS = 100
_MAX_FORM_INPUT_NAMES = 100


class _SurfaceParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: set[str] = set()
        self.forms: list[dict] = []
        self._current_form: dict | None = None

    def handle_starttag(self, tag: str, attrs):
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        tag = tag.lower()
        candidate = ""
        if tag == "a":
            candidate = values.get("href", "")
        elif tag in {"script", "iframe"}:
            candidate = values.get("src", "")
        elif tag == "link":
            candidate = values.get("href", "")
        if candidate and len(self.links) < _MAX_DISCOVERED_LINKS:
            self.links.add(urljoin(self.base_url, candidate))

        if tag == "form" and len(self.forms) < _MAX_DISCOVERED_FORMS:
            action = urljoin(self.base_url, values.get("action") or self.base_url)
            self._current_form = {
                "action": action,
                "method": (values.get("method") or "GET").upper(),
                "input_names": [],
            }
            self.forms.append(self._current_form)
        elif tag in {"input", "textarea", "select"} and self._current_form is not None:
            name = values.get("name", "").strip()
            if name and len(self._current_form["input_names"]) < _MAX_FORM_INPUT_NAMES:
                self._current_form["input_names"].append(name)

    def handle_endtag(self, tag: str):
        if tag.lower() == "form":
            self._current_form = None


def _timeout_seconds() -> float:
    raw = os.getenv("XBOW_RECON_TIMEOUT_SECONDS", "10")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ReconPolicyError("XBOW_RECON_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(value) or not 1.0 <= value <= 30.0:
        raise ReconPolicyError("XBOW_RECON_TIMEOUT_SECONDS must be between 1 and 30")
    return value


def _max_bytes() -> int:
    raw = os.getenv("XBOW_RECON_MAX_BYTES", "262144")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ReconPolicyError("XBOW_RECON_MAX_BYTES must be an integer") from exc
    if not 4096 <= value <= 1_048_576:
        raise ReconPolicyError("XBOW_RECON_MAX_BYTES must be between 4 KiB and 1 MiB")
    return value


def _enabled() -> bool:
    raw = os.getenv("XBOW_ENABLE_RECON", "0").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ReconPolicyError("XBOW_ENABLE_RECON must be a boolean")


def _safe_url(campaign, candidate: str) -> str:
    from .main import is_host_allowed

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ReconPolicyError("recon requires an explicit HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ReconPolicyError("userinfo in recon URLs is forbidden")
    host = parsed.hostname.lower().rstrip(".")
    rules = campaign.target.rules
    if not is_host_allowed(host, rules.allowed_targets, rules.denied_targets):
        raise ReconPolicyError("recon URL is outside declared scope")
    return urlunparse((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", "", "", ""))


def _same_origin(base: str, candidate: str) -> bool:
    left, right = urlparse(base), urlparse(candidate)
    return (
        left.scheme.lower(),
        (left.hostname or "").lower(),
        left.port,
    ) == (
        right.scheme.lower(),
        (right.hostname or "").lower(),
        right.port,
    )


def execute_recon_task(campaign, payload: dict) -> ReconResult:
    kind = str(payload.get("kind") or "")
    if kind not in {"crawl", "map_endpoints", "detect_technology", "map_forms"}:
        raise ReconPolicyError("unsupported recon task kind")
    target = _safe_url(campaign, str(payload.get("target") or ""))
    if not campaign.target.rules.automated_scanning:
        raise ReconPolicyError("automated scanning is disabled")
    if any(
        (
            campaign.target.rules.destructive_testing,
            campaign.target.rules.denial_of_service,
            campaign.target.rules.social_engineering,
            campaign.target.rules.credential_attacks,
        )
    ):
        raise ReconPolicyError("unsafe campaign flags block recon execution")
    if not _enabled():
        return ReconResult(status="dry_run", target=target)

    request = Request(
        target,
        method="GET",
        headers={
            "User-Agent": "xbow-perso-recon/1.0",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
    )
    opener = build_opener(_NoRedirect())
    max_bytes = _max_bytes()
    try:
        with opener.open(request, timeout=_timeout_seconds()) as response:
            body = response.read(max_bytes + 1)[:max_bytes]
            status = int(response.status)
            headers = response.headers
    except HTTPError as exc:
        body = exc.read(max_bytes + 1)[:max_bytes] if exc.fp else b""
        status = int(exc.code)
        headers = exc.headers
    except (URLError, TimeoutError, OSError) as exc:
        return ReconResult(status="error", target=target, error=str(exc))

    content_type = (headers.get("Content-Type") or "").lower() if headers else ""
    text = body.decode("utf-8", errors="replace") if "html" in content_type else ""
    parser = _SurfaceParser(target)
    if text:
        parser.feed(text)

    endpoints = []
    if kind in {"crawl", "map_endpoints"}:
        for candidate in sorted(parser.links):
            try:
                safe = _safe_url(campaign, candidate)
            except ReconPolicyError:
                continue
            if _same_origin(target, safe):
                endpoints.append(safe)

    forms = []
    if kind in {"crawl", "map_forms"}:
        for form in parser.forms:
            if form["method"] not in {"GET", "HEAD"}:
                continue
            try:
                action = _safe_url(campaign, form["action"])
            except ReconPolicyError:
                continue
            if _same_origin(target, action):
                forms.append(
                    {
                        "action": action,
                        "method": form["method"],
                        "input_names": sorted(set(form["input_names"])),
                    }
                )

    technologies = []
    waf = []
    if kind == "detect_technology" and headers:
        for header in ("Server", "X-Powered-By"):
            value = headers.get(header)
            if value:
                technologies.append(f"{header}:{value}"[:200])
        for header in ("CF-Ray", "X-Sucuri-ID", "X-Akamai-Transformed"):
            if headers.get(header):
                waf.append(header)

    return ReconResult(
        status="observed",
        target=target,
        endpoints=tuple(endpoints[:100]),
        forms=tuple(forms[:50]),
        technologies=tuple(sorted(set(technologies))[:20]),
        waf=tuple(sorted(set(waf))[:20]),
        http_status=status,
    )
