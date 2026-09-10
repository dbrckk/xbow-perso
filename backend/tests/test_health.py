from fastapi.responses import JSONResponse

import app.main as main


class HealthyQueue:
    def health(self):
        return {"ok": True, "database": "ok"}


class UnhealthyQueue:
    def health(self):
        return {"ok": False, "database": "corrupt"}


class BrokenQueue:
    def health(self):
        raise RuntimeError("boom")


def test_live_is_dependency_independent():
    result = main.live()
    assert result == {"ok": True, "service": "xbow-perso", "version": main.app.version}


def test_ready_reports_all_dependencies(monkeypatch):
    monkeypatch.setattr(
        main,
        "dependency_readiness",
        lambda: {"ok": True, "database": {"ok": True}, "artifacts": {"ok": True}},
    )
    result = main.ready()
    assert result["ok"] is True
    assert result["database"]["ok"] is True
    assert result["artifacts"]["ok"] is True


def test_ready_returns_503_when_dependency_unhealthy(monkeypatch):
    monkeypatch.setattr(
        main,
        "dependency_readiness",
        lambda: {"ok": False, "database": {"ok": True}, "artifacts": {"ok": False}},
    )
    result = main.ready()
    assert isinstance(result, JSONResponse)
    assert result.status_code == 503


def test_health_reports_database_ok(monkeypatch):
    monkeypatch.setattr(main, "queue", lambda: HealthyQueue())
    result = main.health()
    assert result["ok"] is True
    assert result["database"]["database"] == "ok"


def test_health_returns_503_when_database_unhealthy(monkeypatch):
    monkeypatch.setattr(main, "queue", lambda: UnhealthyQueue())
    result = main.health()
    assert isinstance(result, JSONResponse)
    assert result.status_code == 503


def test_health_returns_503_when_database_probe_raises(monkeypatch):
    monkeypatch.setattr(main, "queue", lambda: BrokenQueue())
    result = main.health()
    assert isinstance(result, JSONResponse)
    assert result.status_code == 503
