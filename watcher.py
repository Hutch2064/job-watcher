"""Collect public ATS JSON, then deterministically rebuild posting history."""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
import gzip
from html import unescape
from html.parser import HTMLParser
import json
import re
import sys
import time
import threading
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

ROOT = Path(__file__).resolve().parent
SOURCES = json.loads((ROOT / "sources.json").read_text())
FIELDS = "posting_id source source_id employer title location remote department posted_date url in_role first_run first_seen last_seen status removed_date experience experience_reason duty_excerpt cover_letter cover_letter_reason".split()
ROLE = re.compile(
    r"\b(portfolio|asset allocation|investment|investing|equity research|fixed.income|credit research|credit analyst|equity analyst|quantitative research|quantitative analyst|fund research|manager research|etf|wealth (?:management|advisor)|financial planning|investment consulting|ocio|multi.asset|systematic|risk analytics|risk analyst|risk analysis|risk reporting|performance analyst|performance analysis|performance attribution|performance reporting|due diligence|investment operations|trade operations|trading operations|operations analyst|operations associate|operations specialist|trade support|corporate actions|fund accounting|fund administration|asset management|research analyst|research associate)\b",
    re.I,
)
EXCLUDE = re.compile(
    r"\b(sales|marketing|administrative assistant|recruiter|tax|auditor|software engineer|cybersecurity|legal counsel)\b",
    re.I,
)

# Accept joined titles such as InvestmentIntern without matching Internal or International.
INTERNSHIP = re.compile(r"intern(?!al|ation|et)(?:ship|s)?", re.I)
PROGRAM = re.compile(r"program(?!m(?:ing|er)|matic)", re.I)
SUMMER = re.compile(r"summer", re.I)


def in_role(title):
    normalized = INTERNSHIP.sub(lambda m: " " + m.group() + " ", title)
    return bool(ROLE.search(normalized) and not EXCLUDE.search(normalized))


class DescriptionText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "li", "br", "div", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("p", "li", "div", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = DescriptionText()
    parser.feed(unescape(value or ""))
    return unescape("".join(parser.parts))


# Select an actual responsibility sentence when available; a missing excerpt is not a negative fit judgment.
DUTY_ACTION = re.compile(
    r"\b(analy[sz]e|analys[ei]s|research|evaluat\w*|monitor\w*|assess\w*|attribut\w*|construct\w*|allocat\w*|optimi[sz]\w*|model\w*|rebalanc\w*|support\w*|perform\w*|conduct\w*|develop\w*|prepare\w*|review\w*|due diligence)\b",
    re.I,
)
DUTY_SUBJECT = re.compile(
    r"\b(portfolio\w*|investment\w*|fund\w*|securit\w*|manager\w*|asset\w*|market\w*|risk\w*|performance|attribution|benchmark\w*|credit|trading|rebalanc\w*)\b",
    re.I,
)
DUTY_START = re.compile(
    r"\b(responsibilities|what you(?:.ll| will) do|what you can expect|key duties|what do .{0,80} do|duties)\b",
    re.I,
)
DUTY_END = re.compile(
    r"\b(qualifications|requirements|what you(?:.ll| will) bring|what will set you apart|benefits|about (?:us|the company)|salary)\b",
    re.I,
)


def duty_excerpt(description):
    lines = [
        re.sub(r"^[•\-*]\s*", "", " ".join(line.split()))
        for line in plain_text(description).splitlines()
    ]
    active = False
    preferred = []
    fallback = []
    for line in lines:
        if len(line) < 90 and DUTY_START.search(line):
            active = True
            continue
        if len(line) < 90 and DUTY_END.search(line):
            active = False
            continue
        if (
            len(line) < 35
            or not DUTY_ACTION.search(line)
            or not DUTY_SUBJECT.search(line)
        ):
            continue
        # Limit the display to one excerpt rather than implying a full job assessment.
        excerpt = line if len(line) <= 240 else line[:237].rstrip() + "…"
        (preferred if active else fallback).append(excerpt)
    return next(iter(preferred or fallback), "")


COVER_TERM = re.compile(
    r"\b(?:cover(?:ing)?[\s-]*letters?|cover[\s-]*notes?|motivation(?:al)?[\s-]*letters?|letters? of (?:motivation|interest))\b",
    re.I,
)


def cover_letter_assessment(description, form=None):
    # A job description or form can change. Only describe the evidence actually observed.
    mentions = [
        line.strip()
        for line in plain_text(description).splitlines()
        if COVER_TERM.search(line)
    ]

    def description_status():
        # Only explicit statements count; generic mentions require review.
        for line in mentions:
            for sentence in re.split(r"(?<=[.!?])\s+", line):
                if not COVER_TERM.search(sentence):
                    continue
                if re.search(
                    r"\b(if|unless|where applicable|when applicable|depending on|if applicable)\b",
                    sentence,
                    re.I,
                ):
                    return (
                        "review",
                        "Job description makes the cover letter conditional",
                    )
                if re.search(
                    r"\b(?:no|without)\s+(?:a\s+)?cover(?:ing)?[\s-]*letters?\b|\bcover(?:ing)?[\s-]*letters?\b.{0,45}\b(?:not required|optional|not necessary)\b",
                    sentence,
                    re.I,
                ):
                    return (
                        "optional",
                        "Job description says a cover letter is optional",
                    )
                if re.search(
                    r"\bcover(?:ing)?[\s-]*letters?\b.{0,45}\b(?:required|mandatory)\b|\b(?:must|requires?|required to)\b.{0,65}\bcover(?:ing)?[\s-]*letters?\b",
                    sentence,
                    re.I,
                ):
                    return (
                        "required",
                        "Job description says a cover letter is required",
                    )
        return (
            ("review", "Description mentions a cover letter; check the application")
            if mentions
            else ("unknown", "Application form not checked")
        )

    described = description_status()
    if not isinstance(form, dict) or not isinstance(form.get("questions"), list):
        return described
    field_names = {
        str(field.get("name") or "")
        for question in form["questions"]
        if isinstance(question, dict)
        for field in (question.get("fields") or [])
        if isinstance(field, dict)
    }
    if not {"first_name", "email"}.issubset(field_names):
        return (
            described
            if mentions
            else ("unknown", "Application form incomplete or unavailable")
        )
    matches = []
    for question in form["questions"]:
        if not isinstance(question, dict):
            continue
        label = plain_text(str(question.get("label") or ""))
        field_description = plain_text(str(question.get("description") or ""))
        label_and_description = label + " " + field_description
        fields = question.get("fields") or []
        names = " ".join(
            str(x.get("name") or "") for x in fields if isinstance(x, dict)
        )
        if not COVER_TERM.search(label_and_description) and not re.search(
            r"cover_?letter", names, re.I
        ):
            continue
        if re.search(
            r"\b(if|unless|where applicable|when applicable|depending on|if applicable)\b",
            label_and_description,
            re.I,
        ):
            return ("review", "Application form makes the cover letter conditional")
        types = {str(x.get("type") or "") for x in fields if isinstance(x, dict)}
        combined = bool(
            re.search(r"\b(resume|r[eé]sum[eé]|cv)\b", label_and_description, re.I)
        ) or bool(re.search(r"\bresume\b", names, re.I))
        if combined or not types.intersection({"input_file", "textarea", "input_text"}):
            return (
                "review",
                "Application form mentions a cover letter; check the field",
            )
        required = question.get("required")
        if required not in (True, False):
            return (
                "review",
                "Application form mentions a cover letter; check the field",
            )
        matches.append(required)
    if any(matches):
        if described[0] == "optional":
            return (
                "review",
                "Form and job description disagree; check the application",
            )
        return ("required", "Required field in employer application form")
    if matches:
        if described[0] == "required":
            return ("review", "Form says optional but job description says required")
        if (
            mentions
            and re.search(
                r"\bplease (?:submit|include|provide|attach)\b",
                " ".join(mentions),
                re.I,
            )
            and described[0] != "optional"
        ):
            return (
                "review",
                "Form says optional but description requests a cover letter",
            )
        return ("optional", "Optional field in employer application form")
    if mentions:
        return described
    return ("not_listed", "No cover-letter field found in the employer form")


SENIOR = re.compile(
    r"\b(senior|sr\.?|staff|lead|principal|director|vice president|avp|vp|svp|evp|head of|chief|partner|managing director)\b",
    re.I,
)
YEARS = re.compile(
    r"\b(?P<min>\d{1,2}|zero|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:(?:-|–|—|to)\s*(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten))?\s*(?:\+|or more)?[\s-]*(?:years?|yrs?)\b",
    re.I,
)
NUMBERS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def experience_level(title, description=""):
    if INTERNSHIP.search(title):
        return ("early", "Internship in title")
    if SENIOR.search(title):
        return ("experienced", "Senior-level title")
    observations = []
    for line in plain_text(description).splitlines():
        line = re.sub(
            r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten)\s*\((\d+)\)",
            r"\1",
            line,
            flags=re.I,
        )
        line = re.sub(r"\b(experience)\.\s+(?=\d)", r"\1: ", line, flags=re.I)
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            for match in YEARS.finditer(sentence):
                context = sentence[max(0, match.start() - 90) : match.end() + 110]
                if not re.search(
                    r"\b(experience|experienced|work history)\b", context, re.I
                ):
                    continue
                # Preferred credentials are useful context but are not minimum requirements.
                preference_context = sentence[
                    max(0, match.start() - 35) : match.end() + 45
                ]
                if re.search(
                    r"\b(preferred|a plus|nice to have|desired|desirable)\b",
                    preference_context,
                    re.I,
                ) and not re.search(
                    r"\b(required|minimum|at least|must have)\b",
                    preference_context,
                    re.I,
                ):
                    continue
                token = match.group("min").lower()
                minimum = int(token) if token.isdigit() else NUMBERS[token]
                if minimum > 40:
                    continue
                observations.append((minimum, " ".join(match.group(0).split())))
    if observations:
        minimum, phrase = max(observations, key=lambda x: x[0])
        if minimum >= 3:
            return ("experienced", f"{phrase} of experience mentioned")
        return ("early", f"{phrase} of experience mentioned")
    if SUMMER.search(title):
        return ("early", "Summer in title")
    if PROGRAM.search(title):
        return ("early", "Program in title")
    return ("unknown", "Experience not determined")


_workday_lock = threading.Lock()
_workday_next_request = 0.0


def retry_after_seconds(error, fallback=20):
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return fallback
    try:
        return max(0, int(value))
    except ValueError:
        try:
            return max(
                0,
                (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds(),
            )
        except (ValueError, TypeError):
            return fallback


def request(url, payload=None):
    global _workday_next_request
    is_workday = ".myworkdayjobs.com/" in url.lower()
    if is_workday:
        with _workday_lock:
            wait = max(0, _workday_next_request - time.monotonic())
            if wait > 120:
                raise RuntimeError(
                    "Workday requested a retry delay longer than this run permits"
                )
            time.sleep(wait)
            interval = 0.6 if "ntrs.wd1.myworkdayjobs.com" in url.lower() else 0.35
            _workday_next_request = time.monotonic() + interval
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "JobWatcher academic project/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if is_workday and error.code == 429:
            with _workday_lock:
                _workday_next_request = max(
                    _workday_next_request, time.monotonic() + retry_after_seconds(error)
                )
        raise


def fetch(source):
    kind, board = source["type"], source["board"]
    if kind == "greenhouse":
        data = request(
            f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        )
        if not isinstance(data.get("jobs"), list):
            raise ValueError("Missing jobs list")
        if len(data["jobs"]) > 5000:
            raise ValueError("Board exceeds 5,000; configure a supported search")

        # Greenhouse's public job-detail JSON includes the actual application questions.
        # A failed form lookup must not fail the board or imply a missing posting.
        def form(job):
            try:
                info = request(
                    f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job['id']}?questions=true"
                )
                if str(info.get("id")) != str(job["id"]) or not isinstance(
                    info.get("questions"), list
                ):
                    return str(job["id"]), None
                return str(job["id"]), info
            except Exception:
                return str(job["id"]), None

        relevant = [
            job for job in data["jobs"] if job.get("title") and in_role(job["title"])
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            data["form_details"] = {
                key: value
                for key, value in pool.map(form, relevant)
                if value is not None
            }
        return data
    if kind == "ukg":
        base = f"https://{source['host']}/{source['tenant']}/JobBoard/{board}"
        pages = []
        offset = 0
        total = None
        while total is None or offset < total:
            payload = {
                "opportunitySearch": {
                    "Top": 50,
                    "Skip": offset,
                    "QueryString": "",
                    "OrderBy": [
                        {
                            "Value": "postedDateDesc",
                            "PropertyName": "PostedDate",
                            "Ascending": False,
                        }
                    ],
                    "Filters": [],
                },
                "matchCriteria": {
                    "PreferredJobs": [],
                    "Educations": [],
                    "LicenseAndCertifications": [],
                    "Skills": [],
                    "hasNoLicenses": False,
                    "SkippedSkills": [],
                },
            }
            page = request(base + "/JobBoardView/LoadSearchResults", payload)
            if not isinstance(page.get("opportunities"), list) or not isinstance(
                page.get("totalCount"), int
            ):
                raise ValueError("Invalid UKG response")
            if total is None:
                total = page["totalCount"]
            if total > 5000:
                raise ValueError("Board exceeds 5,000; configure a supported search")
            if page["totalCount"] != total or (
                offset < total and not page["opportunities"]
            ):
                raise ValueError("Incomplete or changing UKG pagination")
            pages.append(page)
            offset += len(page["opportunities"])
            if total == 0:
                break
        if offset != total:
            raise ValueError("Incomplete UKG board")
        return {"pages": pages}
    if kind == "ashby":
        data = request(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
        if not isinstance(data.get("jobs"), list):
            raise ValueError("Missing jobs list")
        if len(data["jobs"]) > 5000:
            raise ValueError("Board exceeds 5,000; configure a supported search")
        return data
    if kind == "lever":
        data = request(f"https://api.lever.co/v0/postings/{board}?mode=json")
        if not isinstance(data, list):
            raise ValueError("Missing postings list")
        if len(data) > 5000:
            raise ValueError("Board exceeds 5,000; configure a supported search")
        return data
    base = f"https://{source['host']}.myworkdayjobs.com/wday/cxs/{source['host'].split('.')[0]}/{board}/jobs"
    pages, offset, total = [], 0, None
    while total is None or offset < total:
        page = request(
            base,
            {
                "appliedFacets": {},
                "limit": 20,
                "offset": offset,
                "searchText": source.get("search", ""),
            },
        )
        if not isinstance(page.get("jobPostings"), list) or not isinstance(
            page.get("total"), int
        ):
            raise ValueError("Invalid Workday response")
        if total is None:
            total = page["total"]
        if total == 2000:
            raise ValueError(
                "Workday total may be capped at 2,000; partition or configure a verified search"
            )
        if total > 5000 and not source.get("search"):
            raise ValueError("Board exceeds 5,000; configure a search")
        if (page["total"] not in (0, total)) or (
            offset < total and not page["jobPostings"]
        ):
            raise ValueError("Incomplete or changing pagination")
        pages.append(page)
        offset += len(page["jobPostings"])
        if total == 0:
            break
    # Some Workday listings omit a title. Recover it from the public JSON detail,
    # retaining the original page unchanged; fail the board if recovery is impossible.
    recovered_titles = {}
    for page in pages:
        for job in page["jobPostings"]:
            if not job.get("externalPath"):
                print(
                    f"{source['name']}: skipping posting with no external path",
                    file=sys.stderr,
                )
                continue
            if not job.get("title"):
                path = job["externalPath"]
                detail_url = f"https://{source['host']}.myworkdayjobs.com/wday/cxs/{source['host'].split('.')[0]}/{board}{path}"
                info = request(detail_url).get("jobPostingInfo", {})
                title = info.get("title")
                if not title:
                    raise ValueError(
                        f"Workday posting has no recoverable title: {path}"
                    )
                recovered_titles[path] = title
    # Detail lookups enrich relevant roles without jeopardizing the complete board snapshot.
    postings = [
        j
        for page in pages
        for j in page["jobPostings"]
        if j.get("externalPath")
        and (
            (
                in_role(j.get("title") or recovered_titles.get(j["externalPath"], ""))
                and not SENIOR.search(
                    j.get("title") or recovered_titles.get(j["externalPath"], "")
                )
            )
            or re.fullmatch(r"\d+\s+locations?", (j.get("locationsText") or ""), re.I)
        )
    ]

    detail_rate_limited = threading.Event()

    def detail(job):
        if detail_rate_limited.is_set():
            return job["externalPath"], ""
        try:
            url = f"https://{source['host']}.myworkdayjobs.com/wday/cxs/{source['host'].split('.')[0]}/{board}{job['externalPath']}"
            info = request(url).get("jobPostingInfo", {})
            return job["externalPath"], info
        except urllib.error.HTTPError as error:
            if error.code == 429:
                detail_rate_limited.set()
            return job["externalPath"], ""
        except Exception:
            return job["externalPath"], ""

    with ThreadPoolExecutor(
        max_workers=1 if source["id"] == "northerntrust" else 4
    ) as pool:
        details = dict(pool.map(detail, postings))
    return {
        "pages": pages,
        "details": details,
        "recovered_titles": recovered_titles,
        "detail_rate_limited": detail_rate_limited.is_set(),
    }


def utc_date(value):
    if not value:
        return ""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).date().isoformat()
    except (AttributeError, TypeError, ValueError):
        return ""


def normalize_location(value):
    location = re.sub(r"\s+", " ", str(value or "")).strip()
    location = re.sub(
        r",\s*(?:United States of America|United States|USA)$", "", location, flags=re.I
    )
    states = {
        "New York": "NY",
        "Massachusetts": "MA",
        "California": "CA",
        "Illinois": "IL",
        "Texas": "TX",
        "New Jersey": "NJ",
        "Connecticut": "CT",
        "Pennsylvania": "PA",
        "Florida": "FL",
        "Colorado": "CO",
        "Washington": "WA",
    }
    for state, abbreviation in states.items():
        location = re.sub(
            r",\s*" + state + "$", ", " + abbreviation, location, flags=re.I
        )
    return location


def normalize(source, data):
    kind = source["type"]
    rows = []
    if kind in ("greenhouse", "ashby"):
        items = data["jobs"]
    elif kind == "lever":
        items = data
    elif kind == "ukg":
        items = [j for page in data["pages"] for j in page["opportunities"]]
    else:
        items = [j for page in data["pages"] for j in page["jobPostings"]]
    for j in items:
        if kind == "workday" and not j.get("externalPath"):
            continue
        if kind == "greenhouse":
            sid = str(j["id"])
            loc = (j.get("location") or {}).get("name", "")
            dep = ", ".join(d.get("name", "") for d in j.get("departments", []))
            url = j["absolute_url"]
            posted = utc_date(j.get("first_published"))
        elif kind == "ukg":
            if not j.get("Id"):
                raise ValueError("UKG posting has no ID")
            sid = str(j["Id"])
            locations = []
            for item in j.get("Locations", []):
                if isinstance(item, str):
                    label = item
                else:
                    addr = item.get("Address") or {}
                    state = addr.get("State") or {}
                    label = (
                        ", ".join(x for x in (addr.get("City"), state.get("Code")) if x)
                        or item.get("LocalizedDescription")
                        or item.get("LocalizedName")
                        or ""
                    )
                if label and label not in locations:
                    locations.append(label)
            loc = " / ".join(locations)
            dep = j.get("JobCategoryName") or ""
            posted = utc_date(j.get("PostedDate"))
            url = (
                f"https://{source['host']}/{source['tenant']}/JobBoard/{source['board']}/OpportunityDetail?"
                + urlencode({"opportunityId": sid})
            )
        elif kind == "ashby":
            if not j.get("id"):
                raise ValueError("Ashby posting has no ID")
            sid = str(j["id"])
            loc = j.get("location", "")
            dep = j.get("department", "")
            url = j["jobUrl"]
            posted = utc_date(j.get("publishedAt"))
        elif kind == "lever":
            sid = str(j["id"])
            cat = j.get("categories") or {}
            loc = cat.get("location", "")
            dep = cat.get("department") or cat.get("team") or ""
            url = j["hostedUrl"]
            posted = (
                datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc)
                .date()
                .isoformat()
                if j.get("createdAt")
                else ""
            )
        else:
            path = j["externalPath"]
            sid = path.rsplit("_", 1)[-1]
            loc = j.get("locationsText", "")
            dep = ""
            info = data.get("details", {}).get(path, {})
            info = info if isinstance(info, dict) else {}
            posted = utc_date(info.get("startDate") or info.get("postedOn"))
            loc = info.get("location") or loc
            extra = info.get("additionalLocations") or []
            loc = " / ".join(
                normalize_location(x)
                for x in dict.fromkeys([loc] + [x for x in extra if isinstance(x, str)])
                if x
            )
            url = f"https://{source['host']}.myworkdayjobs.com/en-US/{source['board']}{path}"
        title = (
            j["text"]
            if kind == "lever"
            else (
                j["Title"]
                if kind == "ukg"
                else (
                    j.get("title")
                    or data.get("recovered_titles", {}).get(j.get("externalPath", ""))
                    if kind == "workday"
                    else j["title"]
                )
            )
        )
        if not title:
            raise ValueError("Posting title unavailable")
        if kind == "greenhouse":
            description = j.get("content", "")
        elif kind == "ukg":
            description = j.get("BriefDescription") or ""
        elif kind == "ashby":
            description = j.get("descriptionPlain") or j.get("descriptionHtml") or ""
        elif kind == "lever":
            description = " ".join(
                [
                    j.get("descriptionPlain") or j.get("description") or "",
                    j.get("additionalPlain") or j.get("additional") or "",
                ]
                + [
                    x.get("text", "") + " " + (x.get("content") or "")
                    for x in j.get("lists", [])
                ]
            )
        else:
            detail = data.get("details", {}).get(j["externalPath"], "")
            description = (
                detail.get("jobDescription", "") if isinstance(detail, dict) else detail
            )
        loc = normalize_location(loc)
        remote = j.get("isRemote") is True or bool(
            re.search(
                r"\bremote\b",
                " ".join([loc, title, str(j.get("workplaceType") or "")]),
                re.I,
            )
        )
        level, reason = experience_level(title, description)
        form = data.get("form_details", {}).get(sid) if kind == "greenhouse" else None
        cover, cover_reason = cover_letter_assessment(description, form)
        rows.append(
            dict(
                experience=level,
                experience_reason=reason,
                duty_excerpt=duty_excerpt(description) if in_role(title) else "",
                cover_letter=cover,
                cover_letter_reason=cover_reason,
                posting_id=source["id"] + ":" + sid,
                source=source["id"],
                source_id=sid,
                employer=source["name"],
                title=title,
                location=loc or "",
                remote=str(remote).lower(),
                department=dep or "",
                posted_date=posted,
                url=url,
                in_role=str(in_role(title)).lower(),
            )
        )
    if len({r["posting_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate source IDs")
    return rows


def build():
    history = {}
    seen_sources = set()
    dates = set()
    by_id = {s["id"]: s for s in SOURCES}
    for folder in sorted((ROOT / "data/raw").glob("????-??-??")):
        for path in sorted(folder.glob("*.json.gz")):
            source = by_id.get(path.name[:-8])
            if not source:
                print(f"Skipping unknown source: {path}", file=sys.stderr)
                continue
            with gzip.open(path, "rt", encoding="utf-8") as f:
                rows = normalize(source, json.load(f))
            date = folder.name
            dates.add(date)
            first = source["id"] not in seen_sources
            seen_sources.add(source["id"])
            ids = set()
            for row in rows:
                key = row["posting_id"]
                ids.add(key)
                if key not in history:
                    history[key] = {
                        **row,
                        "first_run": str(first).lower(),
                        "first_seen": date,
                        "last_seen": date,
                        "status": "open",
                        "removed_date": "",
                    }
                else:
                    history[key].update(row)
                    history[key].update(last_seen=date, status="open", removed_date="")
            for key, row in history.items():
                if (
                    row["source"] == source["id"]
                    and key not in ids
                    and row["status"] == "open"
                ):
                    row.update(status="removed", removed_date=date)
    target = ROOT / "data/history.csv"
    target.parent.mkdir(exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(history[k] for k in sorted(history))
    return history, dates


def suspect_count(current, previous):
    return previous is not None and previous > 0 and current < previous / 2


def last_good(source_id, before_date):
    for path in sorted(
        (ROOT / "data/raw").glob("????-??-??/" + source_id + ".json.gz"), reverse=True
    ):
        if path.parent.name >= before_date:
            continue
        source = next((item for item in SOURCES if item["id"] == source_id), None)
        if source:
            try:
                with gzip.open(path, "rt", encoding="utf-8") as stream:
                    return path.parent.name, len(normalize(source, json.load(stream)))
            except Exception as exc:
                print(f"Unable to read prior source {path}: {exc}", file=sys.stderr)
    return None, None


def fetch_validated(source, attempts=3):
    for attempt in range(attempts):
        try:
            data = fetch(source)
            return data, normalize(source, data)
        except Exception as exc:
            if attempt == attempts - 1:
                raise
            delay = attempt + 1
            if isinstance(exc, urllib.error.HTTPError) and exc.headers.get(
                "Retry-After"
            ):
                value = exc.headers["Retry-After"]
                try:
                    delay = max(delay, int(value))
                except ValueError:
                    try:
                        delay = max(
                            delay,
                            (
                                parsedate_to_datetime(value)
                                - datetime.now(timezone.utc)
                            ).total_seconds(),
                        )
                    except (ValueError, TypeError):
                        pass
            if delay > 120:
                raise  # Do not retry earlier than the server requested.
            time.sleep(delay)


def write_feed(rows, run_time):
    """Write a feed of recently observed matching positions, excluding baselines."""
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    for key, value in [
        ("title", "Fieldnote Jobs: new investment roles"),
        ("link", "https://hutch2064.github.io/job-watcher/"),
        ("description", "New postings matching the investment role title rule."),
    ]:
        SubElement(channel, key).text = value
    selected = sorted(
        (
            row
            for row in rows
            if row["first_run"] == "false" and row["in_role"] == "true"
        ),
        key=lambda row: (row["first_seen"], row["posting_id"]),
        reverse=True,
    )[:100]
    for row in selected:
        item = SubElement(channel, "item")
        for key, value in [
            ("title", row["title"] + " — " + row["employer"]),
            ("link", row["url"]),
            ("guid", row["posting_id"]),
            ("description", row["location"] + " · First observed " + row["first_seen"]),
        ]:
            element = SubElement(item, key)
            if key == "guid":
                element.set("isPermaLink", "false")
            element.text = value
    ElementTree(rss).write(
        ROOT / "data/feed.xml", encoding="utf-8", xml_declaration=True
    )


def collect():
    now = datetime.now(timezone.utc)
    date = now.date().isoformat()
    folder = ROOT / "data/raw" / date
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        previous = json.loads((ROOT / "data/status.json").read_text())
    except (OSError, ValueError):
        previous = {}
    previous_sources = {
        item.get("id") or item.get("name"): item for item in previous.get("sources", [])
    }

    def collect_one(s):
        path = folder / (s["id"] + ".json.gz")
        last_date, last_count = last_good(s["id"], date)
        try:
            data, rows = fetch_validated(s)
            if suspect_count(len(rows), last_count) and not s.get(
                "accept_count_drop", False
            ):
                raise ValueError(
                    f"Suspect count: {len(rows)} versus {last_count} on {last_date}"
                )
            # Write a complete file atomically; a failed rerun cannot masquerade as today's successful source.
            temp = path.with_suffix(".tmp")
            with temp.open("wb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as out:
                    out.write(
                        json.dumps(
                            data, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    )
            temp.replace(path)
            print(s["name"], len(rows), flush=True)
            return {
                "id": s["id"],
                "name": s["name"],
                "ok": True,
                "count": len(rows),
                "last_success": date,
                "warning": (
                    "Some location and description details were rate-limited"
                    if isinstance(data, dict) and data.get("detail_rate_limited")
                    else ""
                ),
            }
        except Exception as exc:
            print(s["name"], "FAILED", exc, file=sys.stderr, flush=True)
            return {
                "id": s["id"],
                "name": s["name"],
                "ok": False,
                "count": 0,
                "error": str(exc),
                "suspect": str(exc).startswith("Suspect count:"),
                "last_success": date if path.exists() else last_date,
            }

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(
            pool.map(
                collect_one,
                [
                    s
                    for s in SOURCES
                    if s.get("active", True) and s["id"] != "northerntrust"
                ],
            )
        )
    results.extend(
        collect_one(s)
        for s in SOURCES
        if s.get("active", True) and s["id"] == "northerntrust"
    )
    for source in (item for item in SOURCES if not item.get("active", True)):
        last_date, _ = last_good(source["id"], date)
        results.append(
            {
                "id": source["id"],
                "name": source["name"],
                "ok": False,
                "inactive": True,
                "count": 0,
                "last_success": last_date,
                "error": "Inactive: public feed not verified",
            }
        )
    history, dates = build()
    rows = list(history.values())
    write_feed(rows, now.isoformat())
    for result in results:
        source_id = result.get("id")
        prior = previous_sources.get(source_id) or previous_sources.get(
            result["name"], {}
        )
        result["consecutive_failures"] = (
            0
            if result["ok"] or result.get("inactive")
            else 1
            + (
                prior.get("consecutive_failures", 1)
                if not prior.get("ok", True) and not prior.get("inactive")
                else 0
            )
        )
        result["observed_dates"] = [
            path.parent.name
            for path in sorted(
                (ROOT / "data/raw").glob("????-??-??/" + source_id + ".json.gz")
            )
        ][-14:]
    status = {
        "run_time": now.isoformat().replace("+00:00", "Z"),
        "first_run_date": min(dates) if dates else "",
        "days_with_success": len(dates),
        "successful_dates": sorted(dates),
        "open": sum(r["status"] == "open" for r in rows),
        "new_today": sum(
            r["first_seen"] == date and r["first_run"] == "false" for r in rows
        ),
        "removed_today": sum(r["removed_date"] == date for r in rows),
        "sources": results,
    }
    (ROOT / "data/status.json").write_text(json.dumps(status, indent=2) + "\n")
    if not dates:
        raise RuntimeError("No source produced a raw file")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["collect", "build"])
    args = parser.parse_args()
    collect() if args.command == "collect" else build()
