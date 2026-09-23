from collections import Counter

from app.main import app


def _http_route_keys():
    keys=[]
    for route in app.routes:
        path=getattr(route, "path", None)
        methods=getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            keys.append((str(method), str(path)))
    return keys


def test_http_routes_are_registered_once():
    counts=Counter(_http_route_keys())
    duplicates={key:count for key,count in counts.items() if count > 1}

    assert duplicates == {}


def test_previous_duplicate_routes_are_exposed_exactly_once():
    counts=Counter(_http_route_keys())
    for path in (
        "/api/campaigns/{campaign_id}/finding-correlations",
        "/api/campaigns/{campaign_id}/finding-clusters",
        "/api/campaigns/{campaign_id}/report-readiness",
        "/api/campaigns/{campaign_id}/review-queue",
    ):
        assert counts[("GET", path)] == 1
