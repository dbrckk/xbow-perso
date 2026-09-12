from app.main import Campaign, ProgramRules, TargetInput, policy_receipt
from app.policy_integrity import seal_policy_receipt, verify_policy_receipt


def _campaign():
    return Campaign(
        id="c1",
        target=TargetInput(
            name="demo",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="auth-ref",
                allowed_targets=["example.test"],
                automated_scanning=True,
            ),
        ),
    )


def test_policy_receipt_has_stable_hash_without_hmac(monkeypatch):
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)

    receipt = policy_receipt(_campaign(), "example.test", "automated_scan")
    verified = verify_policy_receipt(receipt)

    assert receipt["receipt_hash"]
    assert receipt["integrity_mode"] == "sha256"
    assert receipt["signature"] is None
    assert verified["valid"] is True
    assert verified["hash_valid"] is True
    assert verified["signature_valid"] is None


def test_policy_receipt_detects_tampering(monkeypatch):
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    receipt = policy_receipt(_campaign(), "example.test", "automated_scan")
    receipt["scope_allowed"] = False

    verified = verify_policy_receipt(receipt)

    assert verified["valid"] is False
    assert verified["hash_valid"] is False


def test_policy_receipt_hmac_signature_detects_resealed_tampering(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-secret")
    receipt = policy_receipt(_campaign(), "example.test", "automated_scan")

    assert receipt["integrity_mode"] == "hmac-sha256"
    assert receipt["signature_alg"] == "hmac-sha256"
    assert verify_policy_receipt(receipt)["valid"] is True

    forged = dict(receipt)
    forged["allowed"] = False
    forged = seal_policy_receipt(forged)
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "different-secret")

    verified = verify_policy_receipt(forged)

    assert verified["valid"] is False
    assert verified["signature_valid"] is False


def test_hmac_receipt_fails_closed_without_verification_key(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-secret")
    receipt = policy_receipt(_campaign(), "example.test", "automated_scan")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)

    verified = verify_policy_receipt(receipt)

    assert verified["valid"] is False
    assert verified["hash_valid"] is True
    assert verified["signature_valid"] is None
    assert verified["reason"] == "verification key unavailable"
