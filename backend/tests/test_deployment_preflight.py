from app import main
from app.deployment_preflight import build_deployment_preflight


_ENV_NAMES = (
    "XBOW_ENABLE_PENTAGI",
    "XBOW_ENABLE_ACTIVE_SCANS",
    "XBOW_ENABLE_PENTAGI_WORKER",
    "XBOW_ENABLE_PENTAGI_TRANSPORT",
    "XBOW_ENABLE_PENTAGI_STATUS_WORKER",
    "XBOW_PENTAGI_BASE_URL",
    "XBOW_PENTAGI_MODEL_PROVIDER",
    "DRY_RUN",
    "XBOW_DEPLOYMENT_ENV",
    "XBOW_BACKEND_IMAGE",
    "XBOW_FRONTEND_IMAGE",
    "XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS",
)


def _clear(monkeypatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_preflight_is_ok_with_optional_pentagi_disabled(monkeypatch):
    _clear(monkeypatch)

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "ok"
    assert result["issues"] == []
    assert result["dependencies_ready"] is True
    assert result["pentagi"]["mode"] == "disabled"
    assert result["read_only"] is True
    assert result["contains_secrets"] is False
    assert result["contains_endpoint_values"] is False


def test_preflight_errors_when_core_dependencies_are_not_ready(monkeypatch):
    _clear(monkeypatch)

    result = build_deployment_preflight({"ok": False})

    assert result["status"] == "error"
    assert {
        item["code"] for item in result["issues"]
    } == {"dependencies_not_ready"}


def test_preflight_reports_missing_pentagi_configuration_without_values(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "error"
    codes = {item["code"] for item in result["issues"]}
    assert codes == {
        "pentagi_base_url_missing",
        "pentagi_model_provider_missing",
    }
    assert result["pentagi"]["base_url_configured"] is False
    assert result["pentagi"]["model_provider_configured"] is False


def test_preflight_warns_when_execution_intent_cannot_be_enforced(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_STATUS_WORKER", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_BASE_URL", "https://secret-pentagi.example")
    monkeypatch.setenv("XBOW_PENTAGI_MODEL_PROVIDER", "private-provider")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "warning"
    assert [item["code"] for item in result["issues"]] == [
        "pentagi_execution_intent_not_enforceable"
    ]
    assert result["pentagi"]["base_url_configured"] is True
    assert result["pentagi"]["model_provider_configured"] is True
    assert result["pentagi"]["execution_transport_enforceable"] is False
    rendered = str(result)
    assert "secret-pentagi.example" not in rendered
    assert "private-provider" not in rendered


def test_preflight_warns_on_orphan_pentagi_flags(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_STATUS_WORKER", "true")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "warning"
    assert {item["code"] for item in result["issues"]} == {
        "pentagi_worker_enabled_without_integration",
        "pentagi_transport_enabled_without_integration",
        "pentagi_status_worker_enabled_without_integration",
    }


def test_preflight_reports_invalid_boolean_configuration_fail_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "invalid")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "error"
    assert {item["code"] for item in result["issues"]} == {
        "pentagi_invalid_boolean_configuration"
    }
    assert result["pentagi"]["dispatch_ready"] is False


def test_preflight_endpoint_uses_dependency_readiness(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(main, "dependency_readiness", lambda: {"ok": False})

    result = main.deployment_preflight()

    assert result["status"] == "error"
    assert result["dependencies_ready"] is False
    assert "/api/deployment/preflight" in main.app.openapi()["paths"]


def test_production_preflight_requires_digest_pinned_images(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_DEPLOYMENT_ENV", "production")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "error"
    assert {item["code"] for item in result["issues"]} == {
        "backend_image_digest_missing",
        "frontend_image_digest_missing",
    }
    assert result["deployment_integrity"]["production_mode"] is True
    assert result["deployment_integrity"]["backend_image_digest_configured"] is False
    assert result["deployment_integrity"]["frontend_image_digest_configured"] is False


def test_production_preflight_accepts_digest_pinned_images(monkeypatch):
    _clear(monkeypatch)
    digest = "a" * 64
    monkeypatch.setenv("XBOW_DEPLOYMENT_ENV", "production")
    monkeypatch.setenv("XBOW_BACKEND_IMAGE", f"ghcr.io/example/backend@sha256:{digest}")
    monkeypatch.setenv("XBOW_FRONTEND_IMAGE", f"ghcr.io/example/frontend@sha256:{digest}")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "ok"
    assert result["deployment_integrity"]["production_mode"] is True
    assert result["deployment_integrity"]["backend_image_digest_configured"] is True
    assert result["deployment_integrity"]["frontend_image_digest_configured"] is True


def test_production_preflight_rejects_mutable_tags(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_DEPLOYMENT_ENV", "production")
    monkeypatch.setenv("XBOW_BACKEND_IMAGE", "ghcr.io/example/backend:latest")
    monkeypatch.setenv("XBOW_FRONTEND_IMAGE", "ghcr.io/example/frontend:v1")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "error"
    assert {item["code"] for item in result["issues"]} == {
        "backend_image_digest_missing",
        "frontend_image_digest_missing",
    }


def test_preflight_reports_strict_job_provenance_by_default(monkeypatch):
    _clear(monkeypatch)

    result = build_deployment_preflight({"ok": True})

    assert result["job_provenance"] == {
        "strict_by_default": True,
        "legacy_unprovenanced_jobs_enabled": False,
        "configuration_valid": True,
        "schema": "job-provenance-v1",
    }


def test_preflight_warns_when_legacy_unprovenanced_jobs_are_enabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", "true")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "warning"
    assert "legacy_unprovenanced_jobs_enabled" in {
        item["code"] for item in result["issues"]
    }


def test_preflight_rejects_invalid_legacy_provenance_boolean(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", "maybe")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "error"
    assert "invalid_legacy_provenance_flag" in {
        item["code"] for item in result["issues"]
    }
