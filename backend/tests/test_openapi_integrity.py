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
