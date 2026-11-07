from issues import report_body


def test_report_lists_changes_without_pinging_users():
    status = {"run_time": "2026-11-07T12:00:00Z"}
    rows = [
        dict(
            title="Research @person",
            url="https://example.org/job",
            employer="Firm",
            location="Boston",
            first_seen="2026-11-07",
            first_run="false",
            removed_date="",
        )
    ]
    body = report_body(status, rows)
    assert "## New (1)" in body
    assert "Research &#64;person" in body
    assert "## Removed (0)" in body


def test_health_alerts_exclude_inactive_and_flag_suspect_or_repeat():
    from issues import health_alerts

    status = {
        "sources": [
            {"name": "Inactive", "inactive": True, "consecutive_failures": 9},
            {"name": "One failure", "consecutive_failures": 1},
            {"name": "Repeated", "consecutive_failures": 2},
            {"name": "Sudden drop", "suspect": True, "consecutive_failures": 1},
        ]
    }
    assert [item["name"] for item in health_alerts(status)] == [
        "Repeated",
        "Sudden drop",
    ]
