from app.main import app


def _route_count(path: str, method: str = "GET") -> int:
    method = method.upper()
    return sum(
        1
        for route in app.routes
        if getattr(route, "path", None) == path
        and method in set(getattr(route, "methods", set()) or set())
    )


def test_aggregated_campaign_routes_are_registered_exactly_once():
    for path in (
        "/api/campaigns/{campaign_id}/finding-correlations",
        "/api/campaigns/{campaign_id}/finding-clusters",
        "/api/campaigns/{campaign_id}/report-readiness",
        "/api/campaigns/{campaign_id}/review-queue",
    ):
        assert _route_count(path) == 1, path


def test_openapi_operation_ids_are_unique_for_campaign_routes():
    schema = app.openapi()
    operation_ids = []
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/campaigns/"):
            continue
        for method, operation in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(operation_id)

    assert len(operation_ids) == len(set(operation_ids))
