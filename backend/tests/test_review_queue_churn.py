from app.metrics import build_operational_metrics
from app.operations_dashboard import build_operations_dashboard


class Queue:
    def stats(self):
        return {
            "total": 0,
            "storage": "sqlite",
            "by_status": {},
        }

    def campaign_transition_audit(self, campaign_id):
        return {
            "valid": True,
            "events": 0,
            "invalid_jobs": [],
        }


class Storage:
    def list_campaigns(self):
        return [
            {"id": "c1", "state": "running", "events": []},
            {"id": "c2", "state": "ready", "events": []},
        ]

    def list_artifacts(self, campaign_id):
        return []

    def list_recovery_readiness_snapshots(self, limit=100):
        return []

    def list_review_queue_snapshots(self, campaign_id, limit=100):
        histories = {
            "c1": [
                {
                    "fingerprint": "3" * 64,
                    "document": {
                        "fingerprint": "3" * 64,
                        "task_ids": ["task-b", "task-c"],
                    },
                },
                {
                    "fingerprint": "2" * 64,
                    "document": {
                        "fingerprint": "2" * 64,
                        "task_ids": ["task-a", "task-b"],
                    },
                },
                {
                    "fingerprint": "1" * 64,
                    "document": {
                        "fingerprint": "1" * 64,
                        "task_ids": ["task-a"],
                    },
                },
            ],
            "c2": [
                {
                    "fingerprint": "4" * 64,
                    "document": {
                        "fingerprint": "4" * 64,
                        "task_ids": ["task-x"],
                    },
                }
            ],
        }
        return histories[campaign_id][:limit]


def test_metrics_include_aggregate_review_queue_churn():
    result = build_operational_metrics(Queue(), Storage())

    churn = result["review_queue_churn"]
    assert churn["supported"] is True
    assert churn["campaigns_checked"] == 2
    assert churn["campaigns_with_history"] == 2
    assert churn["retained_snapshots"] == 4
    assert churn["transitions"] == 2
    assert churn["changed_transitions"] == 2
    assert churn["added_tasks"] == 2
    assert churn["removed_tasks"] == 1
    assert churn["change_rate"] == 1.0
    assert churn["retention_limit"] == 100
    assert churn["campaigns_at_capacity"] == 0
    assert churn["read_only"] is True
    assert churn["aggregate_only"] is True
    assert churn["contains_task_ids"] is False


def test_dashboard_surfaces_review_queue_churn_without_changing_health():
    result = build_operations_dashboard(Queue(), Storage())

    churn = result["review_queue_churn"]
    assert churn["retained_snapshots"] == 4
    assert churn["changed_transitions"] == 2
    assert churn["added_tasks"] == 2
    assert churn["removed_tasks"] == 1
    assert churn["change_rate"] == 1.0
    assert "review_queue_churn" not in result["blocked_reasons"]
    assert "review_queue_churn" not in result["degraded_reasons"]
