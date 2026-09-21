from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mobile_api_token_reset_is_vault_only_and_verifies_round_trip():
    script = (ROOT / "scripts" / "mobile-reset-api-token.sh").read_text(encoding="utf-8")

    assert "vault_enabled()" in script
    assert 'set_secret("api_token", token)' in script
    assert "configured_api_token() != token" in script
    assert "/root/xbow-api-token.txt" in script
    assert "openssl rand -hex 32" in script
