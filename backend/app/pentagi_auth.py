from __future__ import annotations

from dataclasses import dataclass

from .secret_vault import SecretVaultError, resolve_secret


class PentagiAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiAuth:
    token: str

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "xbow-perso-pentagi/1.0",
        }


def _validate_token(value: str | None) -> str:
    if value is None:
        raise PentagiAuthError("PentAGI API token is not configured")
    token = value.strip()
    if token != value:
        raise PentagiAuthError("PentAGI API token must not contain surrounding whitespace")
    encoded = token.encode("utf-8")
    if not 16 <= len(encoded) <= 4096:
        raise PentagiAuthError("PentAGI API token length is invalid")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in token):
        raise PentagiAuthError("PentAGI API token contains control characters")
    return token


def load_pentagi_auth() -> PentagiAuth:
    try:
        token = resolve_secret("pentagi_api_token", "XBOW_PENTAGI_API_TOKEN")
    except SecretVaultError as exc:
        raise PentagiAuthError("PentAGI API token is unavailable") from exc
    return PentagiAuth(token=_validate_token(token))
