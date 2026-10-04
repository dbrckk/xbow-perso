from __future__ import annotations

import base64
import re

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


STRIX_CONTRACT_ED25519_DOMAIN = (
    b"xbow:strix-execution-contract:ed25519:v1\x00"
)

_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")


class StrixContractSigningError(RuntimeError):
    pass


def _encode_key(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_key(value: str, *, label: str) -> bytes:
    if not isinstance(value, str) or not _KEY_RE.fullmatch(value):
        raise StrixContractSigningError(
            f"Strix contract {label} key encoding is invalid"
        )
    try:
        raw = base64.urlsafe_b64decode((value + "=").encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise StrixContractSigningError(
            f"Strix contract {label} key encoding is invalid"
        ) from exc
    if len(raw) != 32 or _encode_key(raw) != value:
        raise StrixContractSigningError(
            f"Strix contract {label} key encoding is invalid"
        )
    return raw


def _message(payload: bytes) -> bytes:
    if not isinstance(payload, bytes):
        raise StrixContractSigningError(
            "Strix contract signing payload must be bytes"
        )
    return STRIX_CONTRACT_ED25519_DOMAIN + payload


def derive_strix_contract_public_key(private_key: str) -> str:
    raw_private = _decode_key(private_key, label="private")
    try:
        key = Ed25519PrivateKey.from_private_bytes(raw_private)
        raw_public = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise StrixContractSigningError(
            "Strix contract private key is invalid"
        ) from exc
    return _encode_key(raw_public)


def sign_strix_contract_payload(
    payload: bytes,
    *,
    private_key: str,
) -> str:
    raw_private = _decode_key(private_key, label="private")
    try:
        key = Ed25519PrivateKey.from_private_bytes(raw_private)
        signature = key.sign(_message(payload))
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise StrixContractSigningError(
            "Strix contract private key is invalid"
        ) from exc
    return signature.hex()


def verify_strix_contract_payload(
    payload: bytes,
    *,
    signature: str,
    public_key: str,
) -> None:
    if (
        not isinstance(signature, str)
        or not _SIGNATURE_RE.fullmatch(signature)
    ):
        raise StrixContractSigningError(
            "Strix contract signature encoding is invalid"
        )

    raw_public = _decode_key(public_key, label="public")
    try:
        key = Ed25519PublicKey.from_public_bytes(raw_public)
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise StrixContractSigningError(
            "Strix contract public key is invalid"
        ) from exc

    try:
        key.verify(bytes.fromhex(signature), _message(payload))
    except InvalidSignature as exc:
        raise StrixContractSigningError(
            "Strix contract signature mismatch"
        ) from exc
