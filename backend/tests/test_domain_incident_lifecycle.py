from datetime import datetime, timedelta, timezone

from app.domain_incident_lifecycle import active_incidents_by_domain, apply_domain_incidents


T0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def incident(domain, fingerprint, severity="degraded"):
    return {
        "domain": domain,
        "fingerprint": fingerprint,
        "dedupe_key": f"operational:{domain}:{fingerprint}",
        "severity": severity,
    }


def snapshot(**domains):
    values = {"workload": None, "control_plane": None, "observability": None}
    values.update(domains)
    return {"incidents": values}


def test_multiple_domains_can_be_active_simultaneously():
    history = apply_domain_incidents(
        [],
        snapshot(
            workload=incident("workload", "aaa"),
            observability=incident("observability", "bbb", "critical"),
        ),
        now=T0,
    )
    active = active_incidents_by_domain(history)
    assert active["workload"]["fingerprint"] == "aaa"
    assert active["observability"]["fingerprint"] == "bbb"
    assert active["control_plane"] is None


def test_recovery_of_one_domain_does_not_resolve_another():
    history = apply_domain_incidents(
        [],
        snapshot(
            workload=incident("workload", "aaa"),
            observability=incident("observability", "bbb"),
        ),
        now=T0,
    )
    history = apply_domain_incidents(
        history,
        snapshot(workload=incident("workload", "aaa")),
        now=T0 + timedelta(minutes=1),
    )
    active = active_incidents_by_domain(history)
    assert active["workload"] is not None
    assert active["observability"] is None


def test_changed_fingerprint_rotates_only_its_domain():
    history = apply_domain_incidents(
        [],
        snapshot(
            workload=incident("workload", "old"),
            control_plane=incident("control_plane", "watch"),
        ),
        now=T0,
    )
    history = apply_domain_incidents(
        history,
        snapshot(
            workload=incident("workload", "new", "critical"),
            control_plane=incident("control_plane", "watch"),
        ),
        now=T0 + timedelta(minutes=1),
    )
    active = active_incidents_by_domain(history)
    assert active["workload"]["fingerprint"] == "new"
    assert active["control_plane"]["fingerprint"] == "watch"
    assert len([x for x in history if x["domain"] == "workload"]) == 2


def test_repeated_domain_fingerprint_is_deduplicated():
    history = apply_domain_incidents(
        [], snapshot(workload=incident("workload", "aaa")), now=T0
    )
    history = apply_domain_incidents(
        history,
        snapshot(workload=incident("workload", "aaa")),
        now=T0 + timedelta(seconds=30),
    )
    assert len(history) == 1
    assert history[0]["last_seen_at"] == (T0 + timedelta(seconds=30)).isoformat()
