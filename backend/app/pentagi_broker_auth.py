from __future__ import annotations

from dataclasses import dataclass, field

from .secret_vault import SecretVaultError, resolve_secret


class PentagiBrokerAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiBrokerAuth:
    token: str = field(repr=False)


def _validate_token(value: str | None) -> str:
    if value is None:
        raise PentagiBrokerAuthError("PentAGI broker token is not configured")
    token = value.strip()
    if token != value:
        raise PentagiBrokerAuthError(
            "PentAGI broker token must not contain surrounding whitespace"
        )
    encoded = token.encode("utf-8")
    if not 16 <= len(encoded) <= 4096:
        raise PentagiBrokerAuthError("PentAGI broker token length is invalid")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in token):
        raise PentagiBrokerAuthError("PentAGI broker token contains control characters")
    return token


def load_pentagi_broker_auth() -> PentagiBrokerAuth:
    try:
        token = resolve_secret(
            "pentagi_broker_token",
            "XBOW_PENTAGI_BROKER_TOKEN",
        )
    except SecretVaultError as exc:
        raise PentagiBrokerAuthError("PentAGI broker token is unavailable") from exc
    return PentagiBrokerAuth(token=_validate_token(token))
