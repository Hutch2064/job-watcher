import gzip
import json
import csv
import watcher


def test_conversions():
    samples = [
        (
            {"id": "g", "name": "G", "type": "greenhouse"},
            {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Portfolio Analyst",
                        "location": {"name": "Boston"},
                        "departments": [{"name": "Investments"}],
                        "absolute_url": "https://example.com/1",
                        "first_published": "2025-01-01T00:00:00Z",
                    }
                ]
            },
            "1",
            "Boston",
            "Investments",
            "2025-01-01",
        ),
        (
            {"id": "l", "name": "L", "type": "lever"},
            [
                {
                    "id": "abc",
                    "text": "Investment Analyst",
                    "categories": {"location": "NY", "team": "Research"},
                    "hostedUrl": "https://example.com/2",
                    "createdAt": 1735689600000,
                }
            ],
            "abc",
            "NY",
            "Research",
            "2025-01-01",
        ),
        (
            {
                "id": "w",
                "name": "W",
                "type": "workday",
                "host": "test.wd1",
                "board": "External",
            },
            {
                "pages": [
                    {
                        "jobPostings": [
                            {
                                "title": "ETF Analyst",
                                "externalPath": "/job/City/ETF_R-123",
                                "locationsText": "Chicago",
                            }
                        ]
                    }
                ]
            },
            "R-123",
            "Chicago",
            "",
            "",
        ),
    ]
    for source, data, sid, loc, dep, date in samples:
        row = watcher.normalize(source, data)[0]
        assert (
            row["source_id"],
            row["location"],
            row["department"],
            row["posted_date"],
        ) == (sid, loc, dep, date)
        assert (
            row["posting_id"] == source["id"] + ":" + sid and row["in_role"] == "true"
        )


def test_title_rules():
    for title in [
        "Portfolio Analyst",
        "Investment Solutions Associate",
        "ETF Research Analyst",
        "Fixed Income Analyst",
        "Wealth Management Analyst",
        "Performance Analyst",
        "Risk Analyst",
        "Operational Due Diligence Analyst",
        "Investment Accounting Analyst",
        "Portfolio Reconciliation Analyst",
        "Investment Operations Analyst",
        "Operations Analyst",
        "Corporate Actions Analyst",
        "Research Associate",
        "Fund Accounting Analyst",
    ]:
        assert watcher.in_role(title)
    for title in ["Portfolio Software Engineer", "Sales Associate", "Recruiter"]:
        assert not watcher.in_role(title)


def test_history_removals_failures_and_reappearance(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, "ROOT", tmp_path)
    monkeypatch.setattr(
        watcher,
        "SOURCES",
        [
            {"id": "g", "name": "G", "type": "greenhouse"},
            {"id": "h", "name": "H", "type": "greenhouse"},
        ],
    )

    def write(day, source, ids):
        folder = tmp_path / "data" / "raw" / day
        folder.mkdir(parents=True, exist_ok=True)
        with gzip.open(folder / (source + ".json.gz"), "wt") as f:
            json.dump(
                {
                    "jobs": [
                        {
                            "id": i,
                            "title": "Portfolio Analyst",
                            "absolute_url": f"https://example.com/{i}",
                        }
                        for i in ids
                    ]
                },
                f,
            )

    write("2026-01-01", "g", [1])
    write("2026-01-01", "h", [3])
    write("2026-01-02", "g", [1, 2])
    write("2026-01-03", "g", [2])
    write("2026-01-04", "g", [1])
    h, days = watcher.build()
    assert (
        h["g:1"]["first_run"] == "true"
        and h["g:1"]["first_seen"] == "2026-01-01"
        and h["g:1"]["last_seen"] == "2026-01-04"
        and h["g:1"]["status"] == "open"
        and not h["g:1"]["removed_date"]
    )
    assert (
        h["g:2"]["first_run"] == "false"
        and h["g:2"]["removed_date"] == "2026-01-04"
        and h["g:2"]["last_seen"] == "2026-01-03"
    )
    assert h["h:3"]["status"] == "open" and len(days) == 4
    first = (tmp_path / "data/history.csv").read_bytes()
    watcher.build()
    assert (tmp_path / "data/history.csv").read_bytes() == first


def test_experience_classification():
    classify = watcher.experience_level
    assert (
        classify("Senior Portfolio Analyst", "No experience required")[0]
        == "experienced"
    )
    assert classify("Vice President, Investment Research", "")[0] == "experienced"
    assert classify("Portfolio Analyst, AVP", "")[0] == "experienced"
    assert classify("Lead Portfolio Analyst", "")[0] == "experienced"
    assert (
        classify(
            "Portfolio Analyst", "<p>1-3 years of relevant investment experience</p>"
        )[0]
        == "early"
    )
    assert (
        classify(
            "Investment Analyst", "<li>Minimum of 3+ years of relevant experience</li>"
        )[0]
        == "experienced"
    )
    assert (
        classify("Investment Analyst", "<li>Two years of experience required</li>")[0]
        == "early"
    )
    assert (
        classify("Investment Analyst", "<li>two (2) years of experience required</li>")[
            0
        ]
        == "early"
    )
    assert (
        classify("Investment Analyst", "<li>Five years of experience preferred</li>")[0]
        == "unknown"
    )
    assert (
        classify("Investment Analyst", "We have served clients for 30 years.")[0]
        == "unknown"
    )
    assert (
        classify(
            "Investment Analyst",
            "Experienced candidate with 6 - 8-year post-graduation experience.",
        )[0]
        == "experienced"
    )
    assert (
        classify(
            "Investment Analyst",
            "<p>Experience. 8 years in investment management; 4+ years specializing in active credit.</p>",
        )[0]
        == "experienced"
    )
    assert classify("Associate Portfolio Manager", "")[0] == "unknown"
    assert (
        classify(
            "Portfolio Analyst",
            "1-2 years of experience required. Minimum 5 years of investment experience required.",
        )[0]
        == "experienced"
    )


def test_workday_description_is_reproducible_from_raw():
    source = {
        "id": "w",
        "name": "W",
        "type": "workday",
        "host": "test.wd1",
        "board": "External",
    }
    job = {
        "title": "Investment Analyst",
        "externalPath": "/job/City/role_R-1",
        "locationsText": "City",
    }
    raw = {
        "pages": [{"jobPostings": [job]}],
        "details": {
            job["externalPath"]: "<p>3-5 years of investment experience required.</p>"
        },
    }
    assert watcher.normalize(source, raw)[0]["experience"] == "experienced"
    del raw["details"]
    assert watcher.normalize(source, raw)[0]["experience"] == "unknown"


def test_retry_incomplete_source(monkeypatch):
    calls = []

    def fetch(source):
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("Incomplete pagination")
        return {"jobs": []}

    monkeypatch.setattr(watcher, "fetch", fetch)
    monkeypatch.setattr(watcher.time, "sleep", lambda _: None)
    data, rows = watcher.fetch_validated({"id": "g", "name": "G", "type": "greenhouse"})
    assert len(calls) == 3 and rows == [] and data == {"jobs": []}


def test_early_career_title_signals():
    for title in [
        "Investment Intern",
        "Investment Internship",
        "SummerIntern",
        "investmentinternship",
        "Senior Investment Intern",
    ]:
        assert watcher.experience_level(title, "") == ("early", "Internship in title")
    assert watcher.in_role("InvestmentIntern")
    assert watcher.in_role("PortfolioInternship")
    for title in [
        "International Investment Analyst",
        "Internal Investment Analyst",
        "Internet Investment Analyst",
    ]:
        assert watcher.experience_level(title, "")[0] == "unknown"
    for title in ["Investment Summer Analyst", "Investment Graduate Program"]:
        assert watcher.experience_level(title, "")[0] == "early"
    assert (
        watcher.experience_level("Investment Programming Analyst", "")[0] == "unknown"
    )
    assert (
        watcher.experience_level("Senior Investment Program Manager", "")[0]
        == "experienced"
    )
    assert (
        watcher.experience_level(
            "Investment Summer Program", "5 years of experience required"
        )[0]
        == "experienced"
    )


def test_reported_internships_are_early_not_international():
    for title in [
        "2027 Investment Associate Intern",
        "2027 Quantitative Masters Internship Program - Investments - Portfolio Management - Atlanta",
        "InvestmentInternship",
        "summerINTERN",
    ]:
        assert watcher.experience_level(title) == ("early", "Internship in title")
    for title in ["International Investment Analyst", "Internal Investment Analyst"]:
        assert watcher.experience_level(title)[0] != "early"


def test_workday_recovers_missing_listing_title_without_changing_raw(monkeypatch):
    source = {
        "id": "w",
        "name": "W",
        "type": "workday",
        "host": "test.wd1",
        "board": "External",
    }
    path = "/job/New-York/Analyst_R-42"
    listing = {"externalPath": path, "locationsText": "New York"}

    def request(url, payload=None):
        if payload is not None:
            return {"total": 1, "jobPostings": [listing]}
        return {
            "jobPostingInfo": {
                "title": "Portfolio Analyst",
                "jobDescription": "1 year of investment experience",
            }
        }

    monkeypatch.setattr(watcher, "request", request)
    raw = watcher.fetch(source)
    assert "title" not in raw["pages"][0]["jobPostings"][0]
    assert raw["recovered_titles"][path] == "Portfolio Analyst"
    row = watcher.normalize(source, raw)[0]
    assert row["posting_id"] == "w:R-42" and row["title"] == "Portfolio Analyst"
    assert row["in_role"] == "true" and row["experience"] == "early"


def test_workday_rejects_unrecoverable_title(monkeypatch):
    import pytest

    source = {
        "id": "w",
        "name": "W",
        "type": "workday",
        "host": "test.wd1",
        "board": "External",
    }

    def request(url, payload=None):
        return (
            {"total": 1, "jobPostings": [{"externalPath": "/job/X_R-1"}]}
            if payload is not None
            else {"jobPostingInfo": {}}
        )

    monkeypatch.setattr(watcher, "request", request)
    with pytest.raises(ValueError, match="no recoverable title"):
        watcher.fetch(source)


def test_same_day_rerun_failure_removes_only_that_sources_raw(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    class Clock:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 2, 3, 15, tzinfo=timezone.utc)

    sources = [
        {"id": "a", "name": "A", "type": "greenhouse"},
        {"id": "b", "name": "B", "type": "greenhouse"},
    ]
    monkeypatch.setattr(watcher, "ROOT", tmp_path)
    monkeypatch.setattr(watcher, "SOURCES", sources)
    monkeypatch.setattr(watcher, "datetime", Clock)
    failures = set()

    def fetch(source):
        if source["id"] in failures:
            raise ValueError("source unavailable")
        payload = {
            "jobs": [
                {
                    "id": 1,
                    "title": "Investment Analyst",
                    "absolute_url": "https://example.com/1",
                }
            ]
        }
        return payload, watcher.normalize(source, payload)

    monkeypatch.setattr(watcher, "fetch_validated", fetch)
    watcher.collect()
    folder = tmp_path / "data/raw/2026-02-03"
    assert (folder / "a.json.gz").exists() and (folder / "b.json.gz").exists()
    failures.add("a")
    watcher.collect()
    status = json.loads((tmp_path / "data/status.json").read_text())
    assert (folder / "a.json.gz").exists() and (folder / "b.json.gz").exists()
    assert status["days_with_success"] == 1 and status["successful_dates"] == [
        "2026-02-03"
    ]
    assert status["open"] == 2 and status["sources"][0]["ok"] is False


def test_ashby_normalization_and_duties():
    source = {
        "id": "globalx",
        "name": "Global X",
        "type": "ashby",
        "board": "global-x-etfs",
    }
    payload = {
        "jobs": [
            {
                "id": "abc-123",
                "title": "Investment Operations Analyst",
                "location": "New York, NY",
                "department": "Operations",
                "publishedAt": "2026-11-02T12:10:00Z",
                "jobUrl": "https://jobs.ashbyhq.com/global-x-etfs/abc-123",
                "descriptionPlain": "About us\nWe are a company.\nResponsibilities\nAnalyze portfolio performance and trading activity to support investment decisions.\nRequirements\nTwo years of relevant experience.",
            }
        ]
    }
    row = watcher.normalize(source, payload)[0]
    assert (
        row["posting_id"],
        row["location"],
        row["department"],
        row["posted_date"],
    ) == ("globalx:abc-123", "New York, NY", "Operations", "2026-11-02")
    assert row["in_role"] == "true" and row["experience"] == "early"
    assert (
        row["duty_excerpt"]
        == "Analyze portfolio performance and trading activity to support investment decisions."
    )


def test_workday_refuses_a_potentially_truncated_board(monkeypatch):
    import pytest

    source = {
        "id": "w",
        "name": "W",
        "type": "workday",
        "host": "test.wd1",
        "board": "External",
    }
    monkeypatch.setattr(
        watcher,
        "request",
        lambda *args, **kwargs: {
            "total": 2000,
            "jobPostings": [{"title": "Analyst", "externalPath": "/job/X_1"}],
        },
    )
    with pytest.raises(ValueError, match="may be capped"):
        watcher.fetch(source)


def test_ukg_json_normalization_and_complete_pagination(monkeypatch):
    source = {
        "id": "vaneck",
        "name": "VanEck",
        "type": "ukg",
        "host": "vaneck.rec.pro.ukg.net",
        "tenant": "VAN1502VEAC",
        "board": "board-id",
    }
    job = {
        "Id": "job-123",
        "Title": "Investment Operations Analyst",
        "Locations": [{"Address": {"City": "New York", "State": {"Code": "NY"}}}],
        "JobCategoryName": "Investments",
        "PostedDate": "2026-11-03T09:00:00Z",
        "BriefDescription": "Analyze investment portfolio performance and risk exposures.",
    }
    calls = []

    def request(url, payload=None):
        calls.append(payload["opportunitySearch"]["Skip"])
        return {"opportunities": [job], "totalCount": 1, "locations": []}

    monkeypatch.setattr(watcher, "request", request)
    raw = watcher.fetch(source)
    row = watcher.normalize(source, raw)[0]
    assert (
        calls == [0]
        and row["posting_id"] == "vaneck:job-123"
        and row["location"] == "New York, NY"
    )
    assert row["department"] == "Investments" and row["posted_date"] == "2026-11-03"
    assert (
        row["url"].endswith("OpportunityDetail?opportunityId=job-123")
        and row["in_role"] == "true"
    )
    assert (
        row["duty_excerpt"]
        == "Analyze investment portfolio performance and risk exposures."
    )


def test_cover_letter_evidence_from_form_and_description():
    base = [
        {
            "label": "First Name",
            "required": True,
            "fields": [{"name": "first_name", "type": "input_text"}],
        },
        {
            "label": "Email",
            "required": True,
            "fields": [{"name": "email", "type": "input_text"}],
        },
    ]

    def form(required):
        return {
            "questions": base
            + [
                {
                    "label": "Cover Letter",
                    "required": required,
                    "fields": [{"name": "cover_letter", "type": "input_file"}],
                }
            ]
        }

    assert watcher.cover_letter_assessment("", form(True))[0] == "required"
    assert watcher.cover_letter_assessment("", form(False))[0] == "optional"
    assert watcher.cover_letter_assessment("", {"questions": base})[0] == "not_listed"
    assert watcher.cover_letter_assessment("", {"questions": []})[0] == "unknown"
    assert watcher.cover_letter_assessment("", None)[0] == "unknown"
    assert (
        watcher.cover_letter_assessment("Please submit a cover letter.", form(False))[0]
        == "review"
    )
    assert (
        watcher.cover_letter_assessment("Please submit a cover letter.", None)[0]
        == "review"
    )
    assert (
        watcher.cover_letter_assessment("A cover letter is required.", None)[0]
        == "required"
    )
    assert (
        watcher.cover_letter_assessment("Cover letters are required.", None)[0]
        == "required"
    )
    assert (
        watcher.cover_letter_assessment("No cover letter is required.", None)[0]
        == "optional"
    )
    assert (
        watcher.cover_letter_assessment("A cover letter is required.", form(False))[0]
        == "review"
    )
    assert (
        watcher.cover_letter_assessment("A cover letter is optional.", form(True))[0]
        == "review"
    )
    assert (
        watcher.cover_letter_assessment(
            "A cover letter is required if you are applying from abroad.", None
        )[0]
        == "review"
    )
    combo = {
        "questions": base
        + [
            {
                "label": "Upload resume or cover letter",
                "required": True,
                "fields": [{"name": "question_1", "type": "input_file"}],
            }
        ]
    }
    assert watcher.cover_letter_assessment("", combo)[0] == "review"
    combined_desc = {
        "questions": base
        + [
            {
                "label": "Resume",
                "description": "Attach a cover letter in the same file",
                "required": True,
                "fields": [{"name": "resume", "type": "input_file"}],
            }
        ]
    }
    assert watcher.cover_letter_assessment("", combined_desc)[0] == "review"


def test_greenhouse_form_details_are_retained_and_form_failure_is_isolated(monkeypatch):
    source = {"id": "g", "name": "G", "type": "greenhouse", "board": "demo"}
    jobs = [
        {
            "id": 1,
            "title": "Portfolio Analyst",
            "absolute_url": "https://example.com/1",
        },
        {"id": 2, "title": "Risk Analyst", "absolute_url": "https://example.com/2"},
    ]
    base = [
        {
            "label": "First Name",
            "required": True,
            "fields": [{"name": "first_name", "type": "input_text"}],
        },
        {
            "label": "Email",
            "required": True,
            "fields": [{"name": "email", "type": "input_text"}],
        },
    ]

    def request(url, payload=None):
        if "?content=true" in url:
            return {"jobs": jobs}
        if "/1?" in url:
            return {
                "id": 1,
                "questions": base
                + [
                    {
                        "label": "Cover Letter",
                        "required": True,
                        "fields": [{"name": "cover_letter", "type": "input_file"}],
                    }
                ],
            }
        raise OSError("detail unavailable")

    monkeypatch.setattr(watcher, "request", request)
    raw = watcher.fetch(source)
    rows = watcher.normalize(source, raw)
    assert (
        len(rows) == 2
        and raw["form_details"]["1"]["id"] == 1
        and "2" not in raw["form_details"]
    )
    assert [x["cover_letter"] for x in rows] == ["required", "unknown"]


def test_duty_excerpt_prefers_actual_responsibilities():
    text = "Our investment research model has been used for decades.\nWhat do Investment Associates at Bridgewater do?\nResearch the drivers of economies and markets. Build the insights that inform portfolio decisions.\nQualifications\nExperience in investment research."
    assert watcher.duty_excerpt(text).startswith(
        "Research the drivers of economies and markets."
    )


def test_source_posting_dates_are_utc():
    assert watcher.utc_date("2026-11-02T23:30:00-05:00") == "2026-11-03"
    assert watcher.utc_date("2026-11-03T01:30:00Z") == "2026-11-03"
    assert watcher.utc_date(None) == ""


def test_ukg_fetches_all_pages_and_rejects_incomplete(monkeypatch):
    import pytest

    source = {
        "id": "x",
        "name": "X",
        "type": "ukg",
        "host": "example.com",
        "tenant": "tenant",
        "board": "board",
    }

    def request(url, payload=None):
        skip = payload["opportunitySearch"]["Skip"]
        return {
            "opportunities": [
                {"Id": str(i), "Title": "Analyst"}
                for i in range(skip, min(skip + 50, 51))
            ],
            "totalCount": 51,
        }

    monkeypatch.setattr(watcher, "request", request)
    assert sum(len(p["opportunities"]) for p in watcher.fetch(source)["pages"]) == 51
    monkeypatch.setattr(
        watcher,
        "request",
        lambda url, payload=None: {"opportunities": [], "totalCount": 1},
    )
    with pytest.raises(ValueError, match="Incomplete"):
        watcher.fetch(source)


def test_suspect_drop_guard():
    assert watcher.suspect_count(0, 100)
    assert watcher.suspect_count(49, 100)
    assert not watcher.suspect_count(50, 100)
    assert not watcher.suspect_count(0, None)


def test_unknown_raw_source_is_skipped(tmp_path, monkeypatch):
    import gzip

    monkeypatch.setattr(watcher, "ROOT", tmp_path)
    monkeypatch.setattr(watcher, "SOURCES", [])
    folder = tmp_path / "data/raw/2026-01-01"
    folder.mkdir(parents=True)
    with gzip.open(folder / "retired.json.gz", "wt") as f:
        f.write("{}")
    history, dates = watcher.build()
    assert history == {} and dates == set()


def test_greenhouse_timestamp_is_normalized_to_utc():
    source = {"id": "test", "name": "Test", "type": "greenhouse"}
    raw = {
        "jobs": [
            {
                "id": 1,
                "title": "Investment Analyst",
                "absolute_url": "https://example.org",
                "first_published": "2026-11-06T23:30:00-05:00",
            }
        ]
    }
    assert watcher.normalize(source, raw)[0]["posted_date"] == "2026-11-07"


def test_feed_excludes_initial_snapshot_and_escapes_text(tmp_path, monkeypatch):
    from xml.etree import ElementTree

    monkeypatch.setattr(watcher, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    common = {
        "first_run": "false",
        "in_role": "true",
        "title": "Research & Analysis",
        "employer": "Firm",
        "url": "https://example.org",
        "location": "Boston",
        "first_seen": "2026-11-06",
        "posting_id": "a",
    }
    baseline = {**common, "posting_id": "b", "first_run": "true"}
    watcher.write_feed([common, baseline], "2026-11-07T12:00:00Z")
    items = ElementTree.parse(tmp_path / "data/feed.xml").findall("./channel/item")
    assert len(items) == 1
    assert items[0].findtext("title") == "Research & Analysis — Firm"
