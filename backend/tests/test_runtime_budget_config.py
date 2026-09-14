import pytest

from app.campaign_runtime import campaign_runtime_limit_from_env
from app.planner_budget import planner_budget_from_env


PLANNER_ENV_NAMES = (
    "XBOW_PLANNER_MAX_ACTIONS",
    "XBOW_PLANNER_MAX_SCANS",
    "XBOW_PLANNER_MAX_VALIDATIONS",
    "XBOW_PLANNER_MAX_VALIDATION_BATCH",
    "XBOW_PLANNER_MAX_REPORTS",
    "XBOW_PLANNER_MAX_INFLIGHT_JOBS",
    "XBOW_PLANNER_MAX_FAILED_JOBS",
)


def _clear_planner_env(monkeypatch):
    for name in PLANNER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_planner_budget_from_env_uses_safe_defaults(monkeypatch):
    _clear_planner_env(monkeypatch)

    budget = planner_budget_from_env()

    assert budget.max_actions == 50
    assert budget.max_scans == 3
    assert budget.max_validations == 25
    assert budget.max_validation_batch == 10
    assert budget.max_reports == 5
    assert budget.max_inflight_jobs == 12
    assert budget.max_failed_jobs == 5


def test_planner_budget_from_env_accepts_explicit_limits(monkeypatch):
    monkeypatch.setenv("XBOW_PLANNER_MAX_ACTIONS", "80")
    monkeypatch.setenv("XBOW_PLANNER_MAX_SCANS", "4")
    monkeypatch.setenv("XBOW_PLANNER_MAX_VALIDATIONS", "40")
    monkeypatch.setenv("XBOW_PLANNER_MAX_VALIDATION_BATCH", "8")
    monkeypatch.setenv("XBOW_PLANNER_MAX_REPORTS", "6")
    monkeypatch.setenv("XBOW_PLANNER_MAX_INFLIGHT_JOBS", "16")
    monkeypatch.setenv("XBOW_PLANNER_MAX_FAILED_JOBS", "3")

    budget = planner_budget_from_env()

    assert budget.to_dict() == {
        "max_actions": 80,
        "max_scans": 4,
        "max_validations": 40,
        "max_validation_batch": 8,
        "max_reports": 6,
        "max_inflight_jobs": 16,
        "max_failed_jobs": 3,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("XBOW_PLANNER_MAX_ACTIONS", "0"),
        ("XBOW_PLANNER_MAX_SCANS", "101"),
        ("XBOW_PLANNER_MAX_VALIDATIONS", "bad"),
        ("XBOW_PLANNER_MAX_INFLIGHT_JOBS", "501"),
    ],
)
def test_planner_budget_from_env_rejects_invalid_values(monkeypatch, name, value):
    _clear_planner_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        planner_budget_from_env()


def test_planner_budget_from_env_rejects_batch_above_total(monkeypatch):
    _clear_planner_env(monkeypatch)
    monkeypatch.setenv("XBOW_PLANNER_MAX_VALIDATIONS", "5")
    monkeypatch.setenv("XBOW_PLANNER_MAX_VALIDATION_BATCH", "6")

    with pytest.raises(ValueError, match="max_validation_batch"):
        planner_budget_from_env()


def test_campaign_runtime_limit_from_env_uses_default(monkeypatch):
    monkeypatch.delenv("XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS", raising=False)

    limit = campaign_runtime_limit_from_env()

    assert limit.max_runtime_seconds == 21600


def test_campaign_runtime_limit_from_env_accepts_explicit_value(monkeypatch):
    monkeypatch.setenv("XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS", "3600")

    limit = campaign_runtime_limit_from_env()

    assert limit.max_runtime_seconds == 3600


@pytest.mark.parametrize("value", ["bad", "59", "604801"])
def test_campaign_runtime_limit_from_env_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS", value)

    with pytest.raises(ValueError, match="XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS"):
        campaign_runtime_limit_from_env()
