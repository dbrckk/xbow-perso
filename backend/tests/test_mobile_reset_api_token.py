from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mobile_api_token_reset_is_vault_only_and_verifies_round_trip():
    script = (ROOT / "scripts" / "mobile-reset-api-token.sh").read_text(encoding="utf-8")

    assert "vault_enabled()" in script
    assert 'set_secret("api_token", token)' in script
    assert "configured_api_token() != token" in script
    assert "/root/xbow-api-token.txt" in script
    assert "openssl rand -hex 32" in script



def test_mobile_api_token_reset_loads_distributed_compose_secrets():
    script = (ROOT / "scripts" / "mobile-reset-api-token.sh").read_text(encoding="utf-8")

    assert "XBOW_PRODUCTION_SECRETS_FILE" in script
    assert 'XBOW_POSTGRES_PASSWORD:?missing XBOW_POSTGRES_PASSWORD' in script
    assert 'XBOW_REDIS_PASSWORD:?missing XBOW_REDIS_PASSWORD' in script
    assert 'export XBOW_DATABASE_URL=' in script
    assert 'export XBOW_REDIS_URL=' in script
    assert '"${COMPOSE[@]}" config --quiet' in script
