import warnings

from app.main import app


def test_openapi_operation_ids_are_unique():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = app.openapi()

    operation_ids = []
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                continue
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(operation_id)

    assert len(operation_ids) == len(set(operation_ids))
    duplicate_warnings = [
        str(item.message)
        for item in caught
        if "Duplicate Operation ID" in str(item.message)
    ]
    assert duplicate_warnings == []


def test_core_control_routes_are_present_once_in_openapi():
    schema = app.openapi()
    expected = {
        "/api/campaigns/{campaign_id}/overview",
        "/api/campaigns/{campaign_id}/review-state",
        "/api/campaigns/{campaign_id}/finding-lifecycle",
        "/api/campaigns/{campaign_id}/report-readiness",
    }
    assert expected <= set(schema["paths"])


def test_runtime_routes_do_not_duplicate_method_and_path():
    seen = set()
    duplicates = []

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in sorted(methods):
            key = (method.upper(), path)
            if key in seen:
                duplicates.append(key)
            seen.add(key)

    assert duplicates == []


def test_mutating_routes_are_confined_to_authenticated_api_namespace():
    schema = app.openapi()
    mutating = {"post", "put", "patch", "delete"}

    exposed = []
    for path, path_item in schema["paths"].items():
        for method in path_item:
            if method.lower() in mutating and not path.startswith("/api"):
                exposed.append((method.upper(), path))

    assert exposed == []
