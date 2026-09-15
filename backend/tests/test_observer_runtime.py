from app.observer_runtime import ObserverRuntime, observer_runtime


def test_runtime_returns_same_process_singleton():
    assert observer_runtime() is observer_runtime()


def test_runtime_snapshot_is_detached():
    runtime = ObserverRuntime()
    runtime.health.note_deadline_exceeded()
    first = runtime.snapshot()
    first["deadline_exceeded_count"] = 999
    assert runtime.snapshot()["deadline_exceeded_count"] == 1
