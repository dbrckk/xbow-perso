import base64
import re

import pytest

from app.strix_contract_signing import (
    StrixContractSigningError,
    derive_strix_contract_public_key,
    sign_strix_contract_payload,
    verify_strix_contract_payload,
)


PRIVATE_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
OTHER_PRIVATE_KEY = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode().rstrip("=")


def test_ed25519_contract_signature_round_trip():
    public_key = derive_strix_contract_public_key(PRIVATE_KEY)
    signature = sign_strix_contract_payload(
        b'{"contract":"fixture"}',
        private_key=PRIVATE_KEY,
    )

    assert re.fullmatch(r"[0-9a-f]{128}", signature)
    verify_strix_contract_payload(
        b'{"contract":"fixture"}',
        signature=signature,
        public_key=public_key,
    )


def test_ed25519_contract_signature_rejects_tampering():
    public_key = derive_strix_contract_public_key(PRIVATE_KEY)
    signature = sign_strix_contract_payload(
        b'{"contract":"fixture"}',
        private_key=PRIVATE_KEY,
    )

    with pytest.raises(StrixContractSigningError, match="signature mismatch"):
        verify_strix_contract_payload(
            b'{"contract":"tampered"}',
            signature=signature,
            public_key=public_key,
        )


def test_ed25519_contract_signature_rejects_wrong_public_key():
    public_key = derive_strix_contract_public_key(OTHER_PRIVATE_KEY)
    signature = sign_strix_contract_payload(
        b'{"contract":"fixture"}',
        private_key=PRIVATE_KEY,
    )

    with pytest.raises(StrixContractSigningError, match="signature mismatch"):
        verify_strix_contract_payload(
            b'{"contract":"fixture"}',
            signature=signature,
            public_key=public_key,
        )


@pytest.mark.parametrize(
    "key",
    (
        "",
        "not-base64url",
        base64.urlsafe_b64encode(b"short").decode().rstrip("="),
        base64.urlsafe_b64encode(b"x" * 33).decode().rstrip("="),
        PRIVATE_KEY + "=",
    ),
)
def test_ed25519_contract_signing_rejects_noncanonical_private_key(key):
    with pytest.raises(StrixContractSigningError, match="private key"):
        sign_strix_contract_payload(
            b"fixture",
            private_key=key,
        )


@pytest.mark.parametrize(
    "key",
    (
        "",
        "not-base64url",
        base64.urlsafe_b64encode(b"short").decode().rstrip("="),
        base64.urlsafe_b64encode(b"x" * 33).decode().rstrip("="),
        "A" * 43,
    ),
)
def test_ed25519_contract_verification_rejects_invalid_public_key(key):
    with pytest.raises(StrixContractSigningError, match="public key"):
        verify_strix_contract_payload(
            b"fixture",
            signature="0" * 128,
            public_key=key,
        )


@pytest.mark.parametrize(
    "signature",
    (
        "",
        "0" * 127,
        "0" * 129,
        "A" * 128,
        "z" * 128,
    ),
)
def test_ed25519_contract_verification_rejects_invalid_signature_encoding(signature):
    public_key = derive_strix_contract_public_key(PRIVATE_KEY)

    with pytest.raises(StrixContractSigningError, match="signature encoding"):
        verify_strix_contract_payload(
            b"fixture",
            signature=signature,
            public_key=public_key,
        )


def test_ed25519_public_key_is_canonical_unpadded_base64url():
    public_key = derive_strix_contract_public_key(PRIVATE_KEY)

    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", public_key)
    assert "=" not in public_key
