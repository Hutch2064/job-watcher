from issues import report_body


def test_report_lists_changes_without_pinging_users():
    status = {'run_time': '2026-11-07T12:00:00Z'}
    rows = [dict(title='Research @person', url='https://example.org/job', employer='Firm', location='Boston', first_seen='2026-11-07', first_run='false', removed_date='')]
    body = report_body(status, rows)
    assert '## New (1)' in body
    assert 'Research &#64;person' in body
    assert '## Removed (0)' in body
