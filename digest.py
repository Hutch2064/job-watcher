"""Rank current early-career investment roles and prepare a private Gmail digest.

This program never sends mail. A connected-Gmail scheduled task sends its MIME
payload and records the resulting message ID with ``confirm``. Recipient and
send receipts live in the ignored local state directory, not on GitHub Pages.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
from html import escape
import io
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

from watcher import EXCLUDE, INTERNSHIP, SENIOR

ROOT = Path(__file__).resolve().parent
REPOSITORY = "Hutch2064/job-watcher"
SITE = "https://hutch2064.github.io/job-watcher/"
DEFAULT_STATE = ROOT / ".digest-local"
VERSION = 1
MINIMUM_SCORE = 65
ROUTES = [
    (
        50,
        r"portfolio construction|asset allocation|portfolio optimi[sz]|multi[ -]?asset|model portfolio",
        "Portfolio construction and allocation",
    ),
    (
        47,
        r"portfolio (?:research|analyst|analytics|management analyst)|investment analytics|portfolio solutions",
        "Portfolio research and analytics",
    ),
    (
        45,
        r"quantitative (?:investment|research|analyst)|systematic invest|investment (?:research|strategy)|(?:equity|credit|fixed.income) research|(?:fund|manager|etf) research|due diligence",
        "Investment research and selection",
    ),
    (
        40,
        r"investment (?:analyst|associate|intern)|investing intern|equity analyst|credit analyst|assistant portfolio manager",
        "Investment decision support",
    ),
    (
        34,
        r"performance (?:analyst|attribution)|investment risk|risk analyst|risk analytics",
        "Investment performance and risk",
    ),
    (
        25,
        r"investment operations|trade operations|trading operations|operations (?:analyst|associate)|fund accounting|fund administration",
        "Analytical investment operations",
    ),
]
INVESTMENT = re.compile(
    r"\b(portfolios?|investments?|asset allocation|securities|equities|fixed.income|credit research|funds?|etfs?|managers?|benchmarks?|attribution|trading)\b",
    re.I,
)
ANALYTICAL = re.compile(
    r"\b(analy[sz]\w*|research\w*|construct\w*|allocat\w*|optimi[sz]\w*|model\w*|evaluat\w*|assess\w*|backtest\w*|rebalanc\w*|attribut\w*|due diligence)\b",
    re.I,
)
DEGREE_TRACK = re.compile(r"\b(MBA|Ph\.?D\.?|doctoral|doctorate)\b", re.I)
NON_INVESTMENT = re.compile(
    r"\b(commercial lending|consumer lending|credit card|retail lending|mortgage underwriting)\b",
    re.I,
)


def moment(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def safe_url(value):
    parsed = urlparse(value or "")
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


def rank_job(row, day):
    """100-point discovery score: role 50, experience 35, duties 10, recency 5."""
    title = row.get("title", "")
    normalized = INTERNSHIP.sub(lambda match: " " + match.group() + " ", title)
    if row.get("status") != "open" or row.get("experience") != "early":
        return None
    if SENIOR.search(title) or EXCLUDE.search(title) or DEGREE_TRACK.search(title):
        return None
    if not safe_url(row.get("url")):
        return None
    route = next(
        (
            (points, name)
            for points, pattern, name in ROUTES
            if re.search(pattern, normalized, re.I)
        ),
        None,
    )
    if not route:
        return None
    role_points, route_name = route
    technology_support = bool(
        re.search(
            r"infrastructure|platform enablement|systems? support|application support|software develop|software engineer",
            title,
            re.I,
        )
    )
    if technology_support:
        role_points, route_name = (
            min(role_points, 25),
            "Investment technology supporting portfolio teams",
        )
    duties = row.get("duty_excerpt", "")
    if role_points <= 34 and not INVESTMENT.search(duties + " " + title):
        return None
    if NON_INVESTMENT.search(duties) and not re.search(
        r"portfolio|investment|fund|CLO", duties, re.I
    ):
        return None
    reason = row.get("experience_reason", "")
    if INTERNSHIP.search(title):
        experience_points = 35
        experience_label = "Internship"
    elif re.search(r"\b(?:0|zero|1|one)\b", reason, re.I):
        experience_points = 35
        experience_label = "0–1 years minimum mentioned"
    elif re.search(r"\b(?:2|two)\b", reason, re.I):
        experience_points = 29
        experience_label = "2 years minimum mentioned"
    else:
        experience_points = 30
        experience_label = "Early-career title signal"
    support_duties = bool(
        re.search(
            r"business requirements|usability|system implementation|platform support",
            duties,
            re.I,
        )
    )
    duty_points = (
        10
        if INVESTMENT.search(duties)
        and ANALYTICAL.search(duties)
        and not support_duties
        else 3 if INVESTMENT.search(duties) else 0
    )
    first_seen = row.get("first_seen", "")
    age = (
        (datetime.fromisoformat(day) - datetime.fromisoformat(first_seen)).days
        if first_seen
        else 999
    )
    if age < 0:
        return None
    freshness_points = 5 if age <= 1 else 3 if age <= 7 else 1
    score = role_points + experience_points + duty_points + freshness_points
    if score < MINIMUM_SCORE:
        return None
    return {
        **row,
        "score": score,
        "route": route_name,
        "experience_label": experience_label,
        "breakdown": {
            "role": role_points,
            "experience": experience_points,
            "duties": duty_points,
            "recency": freshness_points,
        },
    }


def select_jobs(rows, status, sent_ids=()):
    day = status["run_time"][:10]
    fresh_sources = {
        item["id"]
        for item in status["sources"]
        if item.get("id")
        and item.get("ok")
        and not item.get("inactive")
        and item.get("last_success", day) == day
    }
    excluded = set(sent_ids)
    ranked = []
    for row in rows:
        if (
            row.get("source") not in fresh_sources
            or row.get("last_seen") != day
            or row.get("posting_id") in excluded
        ):
            continue
        result = rank_job(row, day)
        if result:
            ranked.append(result)
    ranked.sort(
        key=lambda row: (
            -row["score"],
            -row["breakdown"]["role"],
            -datetime.fromisoformat(row["first_seen"]).timestamp(),
            row["posting_id"],
        )
    )
    chosen, identities, urls = [], set(), set()
    for row in ranked:
        identity = (
            row["employer"].casefold(),
            " ".join(row["title"].casefold().split()),
        )
        if identity in identities or row["url"] in urls:
            continue
        chosen.append(row)
        identities.add(identity)
        urls.add(row["url"])
        if len(chosen) == 2:
            break
    return chosen


def email_content(jobs, day, source_time):
    date_label = datetime.fromisoformat(day).strftime("%B %-d, %Y")
    count = len(jobs)
    subject = f"Fieldnote | Investment shortlist - {day}"
    intro = (
        "Two roles worth a closer look."
        if count == 2
        else (
            "One role worth a closer look."
            if count
            else "No new qualifying matches today."
        )
    )
    preheader = (
        " · ".join(f"{job['employer']}: {job['title']}" for job in jobs)
        if jobs
        else "The latest update did not produce an unseen match above your threshold."
    )
    sections = []
    text = [f"FIELDNOTE / DAILY SHORTLIST\n{date_label}\n\nAidan, {intro.lower()}"]
    for index, job in enumerate(jobs, 1):
        e = escape
        cover = {
            "required": "Cover letter required",
            "optional": "Cover letter optional",
        }.get(job.get("cover_letter"), "")
        details = f"{job['experience_label']} · {job.get('location') or 'Location not specified'}"
        breakdown = job["breakdown"]
        why = [job["route"], job.get("experience_reason") or job["experience_label"]]
        if job.get("duty_excerpt"):
            why.append(job["duty_excerpt"])
        sections.append(
            f"""<tr><td style="padding:26px 32px;border-top:1px solid #e1e7e3;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="font-size:12px;letter-spacing:1.1px;color:#596e63;font-weight:700;">0{index} &nbsp; {e(job['employer'])}</td><td align="right" style="font-size:13px;color:#315641;font-weight:700;white-space:nowrap;">{job['score']}/100 fit</td></tr></table>
<h2 style="margin:12px 0 9px;font-family:Arial,Helvetica,sans-serif;font-size:22px;line-height:29px;font-weight:700;color:#142d22;"><a href="{e(job['url'],quote=True)}" style="color:#142d22;text-decoration:none;">{e(job['title'])}</a></h2>
<p style="margin:0 0 18px;font-size:13px;line-height:20px;color:#5c6b63;">{e(details)}{('<br>'+e(cover)) if cover else ''}</p>
<p style="margin:0 0 8px;font-size:13px;font-weight:700;color:#263f31;">Why it made your shortlist</p>
<p style="margin:0 0 6px;font-size:14px;line-height:22px;color:#40554a;">{e(job['route'])}. {e(job.get('experience_reason') or job['experience_label'])}.</p>
{('<p style="margin:0 0 18px;font-size:14px;line-height:22px;color:#40554a;">'+e(job['duty_excerpt'])+'</p>') if job.get('duty_excerpt') else ''}
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td bgcolor="#1e4934" style="border-radius:5px;"><a href="{e(job['url'],quote=True)}" style="display:inline-block;padding:12px 20px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;">View role &amp; apply &rarr;</a></td></tr></table>
<p style="margin:14px 0 0;font-size:11px;line-height:17px;color:#748078;">Role {breakdown['role']}/50 · Experience {breakdown['experience']}/35 · Duties {breakdown['duties']}/10 · Recency {breakdown['recency']}/5</p>
</td></tr>"""
        )
        text.append(
            f"\n{index}. {job['title']}\n{job['employer']} | {details}\nFit score: {job['score']}/100\nWhy: {'; '.join(why)}\n"
            + (cover + "\n" if cover else "")
            + f"View role & apply: {job['url']}\n"
        )
    if not jobs:
        sections.append(
            '<tr><td style="padding:26px 32px;border-top:1px solid #e1e7e3;font-size:15px;line-height:24px;color:#40554a;">The latest update has no unseen roles that clear your relevance and early-career filters. Your next digest will check again after the next daily update.</td></tr>'
        )
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#f2f5f2;font-family:Arial,Helvetica,sans-serif;color:#1c3327;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#f2f5f2;">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f5f2;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid #dce5de;border-radius:8px;">
<tr><td bgcolor="#142d22" style="padding:24px 32px;border-radius:8px 8px 0 0;border-bottom:3px solid #c8a86b;"><p style="margin:0;font-size:13px;font-weight:700;letter-spacing:1.5px;color:#ffffff;">FIELDNOTE <span style="color:#b5c7bd;">/ DAILY SHORTLIST</span></p><p style="margin:8px 0 0;font-size:12px;color:#c0cec5;">{date_label}</p></td></tr>
<tr><td style="padding:28px 32px 24px;"><p style="margin:0 0 9px;font-size:14px;color:#62746a;">Selected for Aidan</p><h1 style="margin:0 0 12px;font-size:28px;line-height:35px;font-weight:700;color:#142d22;">{intro}</h1><p style="margin:0;font-size:15px;line-height:24px;color:#506359;">Ranked for portfolio construction, investment research and an early-career start.</p></td></tr>
{''.join(sections)}
<tr><td style="padding:22px 32px;background:#f7f9f7;border-top:1px solid #e1e7e3;border-radius:0 0 8px 8px;"><p style="margin:0 0 10px;font-size:13px;line-height:21px;"><a href="{SITE}browse.html" style="color:#24553b;text-decoration:underline;">Explore all roles</a> &nbsp;·&nbsp; <a href="{SITE}methods.html" style="color:#24553b;text-decoration:underline;">How matching works</a></p><p style="margin:0;font-size:11px;line-height:18px;color:#748078;">Sources checked {escape(source_time[:10])} UTC. Scores are ranking signals, not hiring probabilities. Review location, work authorization, degree and application requirements with the employer. No geographic restriction is applied. Previously emailed roles are omitted.</p></td></tr>
</table></td></tr></table></body></html>"""
    text.append(
        f"\nExplore all roles: {SITE}browse.html\nScores rank relevance; they are not hiring probabilities. Check location, work authorization, degree and full requirements. No geographic restriction is applied. Previously emailed roles are omitted.\nSources checked {source_time[:10]} UTC."
    )
    return subject, html, "\n".join(text)


def gh_json(*args):
    return json.loads(subprocess.check_output(["gh", *args], text=True))


def remote_update(now=None, sent_dates=()):
    now = now or datetime.now(timezone.utc)
    runs = gh_json(
        "run",
        "list",
        "--repo",
        REPOSITORY,
        "--workflow",
        "daily.yml",
        "--limit",
        "30",
        "--json",
        "databaseId,createdAt,updatedAt,status,conclusion",
    )
    commit = gh_json("api", f"repos/{REPOSITORY}/commits/main")["sha"]

    def contents(name):
        return subprocess.check_output(
            [
                "gh",
                "api",
                "-H",
                "Accept: application/vnd.github.raw+json",
                f"repos/{REPOSITORY}/contents/{name}?ref={commit}",
            ],
            text=True,
        )

    status = json.loads(contents("data/status.json"))
    collected = moment(status["run_time"])
    matching = [
        run
        for run in runs
        if run["status"] == "completed"
        and run["conclusion"] == "success"
        and moment(run["createdAt"]) <= collected <= moment(run["updatedAt"])
    ]
    if not matching:
        return None, "The latest data has no confirmed successful daily workflow yet"
    if (now - collected).total_seconds() > 36 * 3600 or collected > now:
        return (
            None,
            "The latest completed daily update is too old or has an invalid timestamp",
        )
    if status["run_time"][:10] in sent_dates:
        return None, "This UTC update day has already been emailed"
    rows = list(csv.DictReader(io.StringIO(contents("data/history.csv"))))
    return {
        "status": status,
        "rows": rows,
        "commit": commit,
        "workflow_run_id": matching[0]["databaseId"],
    }, ""


def read_state(directory):
    path = directory / "state.json"
    return (
        json.loads(path.read_text())
        if path.exists()
        else {"sent_dates": {}, "sent_job_ids": [], "pending": None}
    )


def write_private(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.chmod(0o600)
    temporary.replace(path)


def write_state(directory, state):
    write_private(directory / "state.json", json.dumps(state, indent=2) + "\n")


def prepare(directory, recipient, update):
    state = read_state(directory)
    if state.get("pending"):
        pending = state["pending"]
        if pending["recipient"] != recipient:
            raise ValueError(
                "Resolve the existing recipient reservation before changing recipients"
            )
        return {
            "action": "reconcile",
            "subject": pending["subject"],
            "digest_id": pending["digest_id"],
            "status": pending["status"],
            "payload_path": str(directory / "delivery.json"),
        }
    status = update["status"]
    day = status["run_time"][:10]
    if day in state["sent_dates"]:
        return {
            "action": "skip",
            "reason": "This UTC update day has already been emailed",
            "day": day,
        }
    jobs = select_jobs(update["rows"], status, state["sent_job_ids"])
    subject, html, plain = email_content(jobs, day, status["run_time"])
    digest_id = hashlib.sha256(
        (
            day + str(update["workflow_run_id"]) + recipient + subject + html + plain
        ).encode()
    ).hexdigest()[:24]
    delivery = {
        "to": recipient,
        "subject": subject,
        "payload": {
            "mime_type": "multipart/alternative",
            "parts": [
                {
                    "mime_type": "text/plain",
                    "charset": "utf-8",
                    "body": {"content": plain},
                },
                {
                    "mime_type": "text/html",
                    "charset": "utf-8",
                    "body": {"content": html},
                },
            ],
        },
    }
    write_private(directory / "delivery.json", json.dumps(delivery, indent=2) + "\n")
    write_private(directory / "preview.html", html)
    write_private(
        directory / "selection.json",
        json.dumps(
            {
                "version": VERSION,
                "day": day,
                "digest_id": digest_id,
                "workflow_run_id": update["workflow_run_id"],
                "commit": update["commit"],
                "jobs": jobs,
            },
            indent=2,
        )
        + "\n",
    )
    state["pending"] = {
        "digest_id": digest_id,
        "day": day,
        "workflow_run_id": update["workflow_run_id"],
        "subject": subject,
        "recipient": recipient,
        "job_ids": [row["posting_id"] for row in jobs],
        "status": "reserved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_state(directory, state)
    return {
        "action": "ready",
        "digest_id": digest_id,
        "subject": subject,
        "day": day,
        "payload_path": str(directory / "delivery.json"),
        "preview_path": str(directory / "preview.html"),
        "job_count": len(jobs),
        "jobs": [
            {
                "title": row["title"],
                "employer": row["employer"],
                "score": row["score"],
                "url": row["url"],
            }
            for row in jobs
        ],
    }


def claim(directory, digest_id):
    state = read_state(directory)
    pending = state.get("pending")
    if (
        not pending
        or pending["digest_id"] != digest_id
        or pending["status"] != "reserved"
    ):
        raise ValueError(
            "No matching unsent reservation; reconcile Gmail before retrying"
        )
    pending["status"] = "sending"
    write_state(directory, state)
    return {
        "action": "send",
        "payload_path": str(directory / "delivery.json"),
        "digest_id": digest_id,
    }


def discard(directory, digest_id):
    state = read_state(directory)
    pending = state.get("pending")
    if (
        not pending
        or pending["digest_id"] != digest_id
        or pending["status"] != "reserved"
    ):
        raise ValueError(
            "Only an unsent reserved digest can be discarded; reconcile any sending attempt first"
        )
    state["pending"] = None
    write_state(directory, state)
    return {"action": "discarded", "digest_id": digest_id}


def confirm(directory, digest_id, message_id):
    state = read_state(directory)
    pending = state.get("pending")
    if not pending or pending["digest_id"] != digest_id or not message_id.strip():
        raise ValueError("A matching digest and Gmail message ID are required")
    state["sent_dates"][pending["day"]] = {
        "digest_id": digest_id,
        "message_id": message_id,
        "workflow_run_id": pending["workflow_run_id"],
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    state["sent_job_ids"] = sorted(set(state["sent_job_ids"] + pending["job_ids"]))
    state["pending"] = None
    write_state(directory, state)
    return {"action": "confirmed", "message_id": message_id, "day": pending["day"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "claim", "confirm", "discard"])
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--recipient")
    parser.add_argument("--digest-id")
    parser.add_argument("--message-id")
    args = parser.parse_args()
    directory = args.state_dir.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    with (directory / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == "prepare":
            config_path = directory / "config.json"
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            recipient = args.recipient or config.get("recipient")
            if not recipient or not re.fullmatch(
                r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient
            ):
                raise ValueError(
                    "Set a recipient in private config.json or --recipient"
                )
            if args.recipient:
                write_private(
                    config_path, json.dumps({"recipient": recipient}, indent=2) + "\n"
                )
            if read_state(directory).get("pending"):
                output = prepare(directory, recipient, {})
            else:
                update, reason = remote_update(
                    sent_dates=read_state(directory)["sent_dates"]
                )
                output = (
                    prepare(directory, recipient, update)
                    if update
                    else {"action": "skip", "reason": reason}
                )
        elif args.command == "claim":
            output = claim(directory, args.digest_id)
        elif args.command == "discard":
            output = discard(directory, args.digest_id)
        else:
            output = confirm(directory, args.digest_id, args.message_id or "")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
