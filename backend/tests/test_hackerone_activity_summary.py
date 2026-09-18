from app.hackerone_report_tracking import project_public_report_activities


def _activity(activity_id, activity_type, *, message="", internal=False, **extra):
    return {
        "id": activity_id,
        "type": activity_type,
        "attributes": {
            "report_id": "4242",
            "message": message,
            "internal": internal,
            "created_at": "2026-09-18T20:30:00Z",
            "updated_at": "2026-09-18T20:31:00Z",
            **extra,
        },
        "relationships": {
            "actor": {
                "data": {
                    "id": "sensitive-user-id",
                    "type": "user",
                    "attributes": {"username": "triager"},
                }
            },
            "attachments": {
                "data": [
                    {
                        "id": "attachment-1",
                        "type": "attachment",
                        "attributes": {"file_name": "secret.txt"},
                    }
                ]
            },
        },
    }


def _document(activities):
    return {
        "data": {
            "id": "4242",
            "type": "report",
            "attributes": {"state": "triaged"},
            "relationships": {"activities": {"data": activities}},
        }
    }


def test_public_activity_projection_is_allowlisted_bounded_and_redacted():
    result = project_public_report_activities(
        _document(
            [
                _activity(
                    "a1",
                    "activity-comment",
                    message="Public comment",
                ),
                _activity(
                    "a2",
                    "activity-bounty-awarded",
                    message="Bounty awarded",
                    bounty_amount="500",
                    bonus_amount="50",
                ),
                _activity(
                    "a3",
                    "activity-bug-duplicate",
                    message="Duplicate",
                    original_report_id=1336,
                ),
                _activity(
                    "a4",
                    "activity-bug-informative",
                    message="Informative",
                ),
                _activity(
                    "a5",
                    "activity-bug-resolved",
                    message="Resolved",
                ),
            ]
        ),
        expected_report_id="4242",
    )

    assert [item["activity_type"] for item in result] == [
        "activity-comment",
        "activity-bounty-awarded",
        "activity-bug-duplicate",
        "activity-bug-informative",
        "activity-bug-resolved",
    ]
    assert result[0]["message"] == "Public comment"
    assert result[1]["bounty_amount"] == "500"
    assert result[1]["bonus_amount"] == "50"
    assert result[2]["original_report_id"] == "1336"
    assert "relationships" not in str(result)
    assert "sensitive-user-id" not in str(result)
    assert "attachment-1" not in str(result)


def test_public_activity_projection_ignores_internal_and_unknown_types():
    result = project_public_report_activities(
        _document(
            [
                _activity(
                    "a1",
                    "activity-comment",
                    message="Internal",
                    internal=True,
                ),
                _activity(
                    "a2",
                    "activity-bounty-suggested",
                    message="Internal program data",
                    internal=True,
                ),
                _activity(
                    "a3",
                    "activity-something-new",
                    message="Unknown",
                ),
            ]
        ),
        expected_report_id="4242",
    )

    assert result == []


def test_public_activity_projection_caps_count_and_message_length():
    records = [
        _activity(
            str(index),
            "activity-comment",
            message="x" * 9000,
        )
        for index in range(30)
    ]

    result = project_public_report_activities(
        _document(records),
        expected_report_id="4242",
    )

    assert len(result) == 20
    assert all(len(item["message"]) == 8192 for item in result)
