import json
from datetime import datetime, timezone

import pytest

import digest

DAY = "2026-11-07"


def job(**changes):
    row = dict(
        posting_id="a:1",
        source="a",
        source_id="1",
        employer="Example Investments",
        title="Portfolio Construction Analyst",
        location="New York, NY",
        url="https://example.com/jobs/1",
        status="open",
        in_role="true",
        experience="early",
        experience_reason="0-2 years of experience mentioned",
        duty_excerpt="Analyze investment portfolios and model asset allocation to support investment decisions.",
        first_seen=DAY,
        last_seen=DAY,
        first_run="false",
        cover_letter="optional",
    )
    row.update(changes)
    return row


def status():
    return {
        "run_time": DAY + "T18:00:00Z",
        "sources": [{"id": "a", "name": "Example", "ok": True, "last_success": DAY}],
    }


def test_rank_prioritizes_portfolio_work_and_excludes_experienced_or_degree_tracks():
    core = digest.rank_job(job(), DAY)
    operations = digest.rank_job(job(title="Investment Operations Analyst"), DAY)
    assert core["score"] > operations["score"]
    assert core["score"] == 100
    assert digest.rank_job(job(title="Senior Portfolio Analyst"), DAY) is None
    assert (
        digest.rank_job(
            job(experience="experienced", experience_reason="3 years required"), DAY
        )
        is None
    )
    assert digest.rank_job(job(experience="unknown"), DAY) is None
    assert digest.rank_job(job(title="MBA Portfolio Construction Intern"), DAY) is None
    assert (
        digest.rank_job(
            job(title="Portfolio Construction Analyst", url="javascript:alert(1)"), DAY
        )
        is None
    )


def test_select_current_active_unseen_distinct_postings_only():
    rows = [
        job(),
        job(posting_id="a:2", url="https://example.com/jobs/2"),
        job(
            posting_id="a:3",
            title="Investment Research Intern",
            url="https://example.com/jobs/3",
        ),
        job(posting_id="b:1", source="b", title="Portfolio Analyst"),
    ]
    selected = digest.select_jobs(rows, status())
    assert [x["posting_id"] for x in selected] == ["a:1", "a:3"]
    assert not digest.select_jobs([job(last_seen="2026-11-06")], status())
    assert not digest.select_jobs(
        [job()], {"run_time": DAY + "T18:00:00Z", "sources": [{"id": "a", "ok": False}]}
    )
    assert not digest.select_jobs([job()], status(), sent_ids=["a:1"])


def test_email_has_direct_links_plain_alternative_and_escaped_source_text():
    selected = digest.select_jobs([job(title="Portfolio Analyst <script>")], status())
    subject, html, plain = digest.email_content(selected, DAY, status()["run_time"])
    assert subject.endswith(DAY)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert (
        "https://example.com/jobs/1" in plain
        and 'href="https://example.com/jobs/1"' in html
    )
    assert "View role &amp; apply" in html
    assert "No new qualifying" in digest.email_content([], DAY, status()["run_time"])[1]


def test_prepare_does_not_mark_sent_and_uncertain_sends_are_blocked(tmp_path):
    update = {
        "status": status(),
        "rows": [job()],
        "commit": "abc",
        "workflow_run_id": 123,
    }
    result = digest.prepare(tmp_path, "recipient@example.com", update)
    assert result["action"] == "ready"
    assert digest.read_state(tmp_path)["sent_dates"] == {}
    payload = json.loads((tmp_path / "delivery.json").read_text())
    assert payload["payload"]["mime_type"] == "multipart/alternative"
    assert len(payload["payload"]["parts"]) == 2
    assert (
        digest.prepare(tmp_path, "recipient@example.com", update)["action"]
        == "reconcile"
    )
    digest.claim(tmp_path, result["digest_id"])
    with pytest.raises(ValueError):
        digest.claim(tmp_path, result["digest_id"])
    with pytest.raises(ValueError):
        digest.confirm(tmp_path, result["digest_id"], "")
    digest.confirm(tmp_path, result["digest_id"], "gmail-message-123")
    assert digest.prepare(tmp_path, "recipient@example.com", update)["action"] == "skip"
    assert digest.read_state(tmp_path)["sent_job_ids"] == ["a:1"]


def test_remote_update_waits_until_matching_workflow_success(monkeypatch):
    monkeypatch.setattr(
        digest,
        "gh_json",
        lambda *args: (
            [
                {
                    "databaseId": 123,
                    "createdAt": DAY + "T17:00:00Z",
                    "updatedAt": DAY + "T19:00:00Z",
                    "status": "in_progress",
                    "conclusion": "",
                }
            ]
            if args[0] == "run"
            else {"sha": "abc"}
        ),
    )
    monkeypatch.setattr(
        digest.subprocess, "check_output", lambda *args, **kwargs: json.dumps(status())
    )
    data, reason = digest.remote_update(datetime(2026, 11, 7, 20, tzinfo=timezone.utc))
    assert data is None and "successful" in reason


def test_portfolio_team_technology_does_not_outrank_direct_portfolio_work():
    direct = digest.rank_job(job(title="Analyst, Multi-Asset Portfolio Solutions"), DAY)
    support = digest.rank_job(
        job(
            title="Models Infrastructure Platform Enablement, Multi-Asset Strategies, Analyst",
            duty_excerpt="Gather and analyze business requirements to improve systems for Portfolio Managers.",
        ),
        DAY,
    )
    assert direct["score"] > support["score"]
    assert support["breakdown"]["role"] == 25
