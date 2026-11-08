"""Deliver the daily shortlist in GitHub Actions, without an AI runtime.

The separate private Git repository is a durable outbox. Persist the exact
request and a sending reservation before contacting Resend. Retries use the same
idempotency key and bytes; an unresolved attempt older than 23 hours fails closed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parseaddr
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request
from uuid import UUID

import digest

STATE_REPOSITORY = "Hutch2064/job-watcher-delivery"
RETRY_WINDOW_SECONDS = 23 * 3600  # Resend retains idempotency keys for 24 hours.
PRIVATE_FILES = [
    "state.json",
    "selection.json",
    "delivery.json",
    "preview.html",
    "provider.json",
    "provider-check.json",
]


def valid_address(address):
    return bool(re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", address))


def configuration():
    recipient = os.environ.get("DIGEST_TO", "").strip()
    sender = os.environ.get("DIGEST_FROM", "").strip()
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not valid_address(recipient):
        raise ValueError("Configure the private DIGEST_TO repository secret")
    if "\r" in sender or "\n" in sender or not valid_address(parseaddr(sender)[1]):
        raise ValueError("Configure the verified DIGEST_FROM repository secret")
    if not api_key:
        raise ValueError("Configure the RESEND_API_KEY repository secret")
    return recipient, sender, api_key


def load_delivery_state(directory):
    # Never silently initialize an empty ledger: that could resend past digests.
    path = directory / "state.json"
    if not path.is_file():
        raise ValueError("Private delivery history is missing; refusing to send")
    state = json.loads(path.read_text())
    if (
        not isinstance(state.get("sent_dates"), dict)
        or not isinstance(state.get("sent_job_ids"), list)
        or "pending" not in state
    ):
        raise ValueError("Private delivery history is invalid; refusing to send")
    return state


def git(directory, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(directory), *arguments], text=True, stderr=subprocess.PIPE
    ).strip()


def persist_outbox(directory):
    """Push the private outbox before sending, and the receipt after acceptance."""
    if (
        Path(git(directory, "rev-parse", "--show-toplevel")).resolve()
        != directory.resolve()
    ):
        raise ValueError("Delivery history must have its own private Git checkout")
    remote = git(directory, "remote", "get-url", "origin").removesuffix(".git")
    if remote not in {
        f"git@github.com:{STATE_REPOSITORY}",
        f"https://github.com/{STATE_REPOSITORY}",
    }:
        raise ValueError(
            "Refusing to publish delivery history to an unexpected repository"
        )
    git(directory, "config", "user.name", "Fieldnote delivery")
    git(
        directory,
        "config",
        "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com",
    )
    existing = [name for name in PRIVATE_FILES if (directory / name).is_file()]
    git(directory, "add", "--", *existing)
    changed = subprocess.run(
        ["git", "-C", str(directory), "diff", "--cached", "--quiet"], check=False
    ).returncode
    if changed not in (0, 1):
        raise RuntimeError("Could not inspect private delivery history")
    if changed:
        git(
            directory,
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Update private delivery outbox",
        )
    # Push even when there is no new diff, to retry a previously failed push.
    git(directory, "push", "origin", "HEAD:main")


def provider_payload(directory, recipient, sender):
    state = load_delivery_state(directory)
    pending = state.get("pending")
    selection = json.loads((directory / "selection.json").read_text())
    delivery = json.loads((directory / "delivery.json").read_text())
    if (
        not pending
        or pending["recipient"] != recipient
        or delivery.get("to") != recipient
        or set(delivery) != {"to", "subject", "payload"}
        or selection.get("digest_id") != pending["digest_id"]
        or selection.get("version") != digest.VERSION
        or selection.get("day") != pending["day"]
        or delivery.get("subject")
        != f"Fieldnote | Investment shortlist - {pending['day']}"
    ):
        raise ValueError(
            "Reserved content does not match the private delivery reservation"
        )
    jobs = selection.get("jobs", [])
    if len(jobs) > digest.MAXIMUM_JOBS or any(
        not digest.location_eligibility(job) for job in jobs
    ):
        raise ValueError("Reserved jobs fail the five-role remote-or-Texas policy")
    mime = delivery["payload"]
    parts = mime.get("parts", [])
    if (
        mime.get("mime_type") != "multipart/alternative"
        or len(parts) != 2
        or sorted(part.get("mime_type", "") for part in parts)
        != ["text/html", "text/plain"]
        or any(part.get("parts") for part in parts)
    ):
        raise ValueError("Expected one HTML and one plain-text alternative")
    content = {part["mime_type"]: part["body"]["content"] for part in parts}
    if not all(isinstance(value, str) and value for value in content.values()):
        raise ValueError("Email alternatives must both contain text")
    return {
        "from": sender,
        "to": [recipient],
        "subject": delivery["subject"],
        "html": content["text/html"],
        "text": content["text/plain"],
        "tags": [{"name": "application", "value": "fieldnote"}],
    }


def send_resend(api_key, payload, idempotency_key):
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "User-Agent": "Fieldnote-Digest/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # Provider bodies can echo recipient addresses; keep public logs private.
        raise RuntimeError(
            f"Mail provider returned HTTP {error.code}; outbox preserved"
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError(
            "Mail provider outcome is uncertain; outbox preserved for an idempotent retry"
        ) from None
    message_id = result.get("id")
    try:
        UUID(message_id)
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError(
            "Mail provider returned no valid receipt; outbox preserved"
        ) from None
    return message_id


def run(
    directory,
    recipient,
    sender,
    api_key,
    *,
    dry_run=False,
    now=None,
    fetch_update=digest.remote_update,
    persist=persist_outbox,
    send=send_resend,
):
    now = now or datetime.now(timezone.utc)
    state = load_delivery_state(directory)
    if not state.get("pending"):
        update, reason = fetch_update(now=now, sent_dates=state["sent_dates"])
        if not update:
            return {"action": "skip", "reason": reason}
        if dry_run:
            jobs = digest.select_jobs(
                update["rows"], update["status"], state["sent_job_ids"]
            )
            return {
                "action": "dry-run",
                "day": update["status"]["run_time"][:10],
                "job_count": len(jobs),
            }
        prepared = digest.prepare(directory, recipient, update)
        if prepared["action"] == "skip":
            return {"action": "skip", "reason": prepared["reason"]}
    state = load_delivery_state(directory)
    pending = state["pending"]
    if pending["day"] in state["sent_dates"]:
        raise ValueError("A pending outbox conflicts with an existing sent-day receipt")
    payload = provider_payload(directory, recipient, sender)
    if dry_run:
        return {
            "action": "dry-run",
            "day": pending["day"],
            "job_count": len(pending["job_ids"]),
        }
    if pending["status"] == "reserved":
        digest.claim(directory, pending["digest_id"])
        state = load_delivery_state(directory)
        pending = state["pending"]
        pending["provider"] = "resend"
        pending["first_attempt_at"] = now.isoformat()
        digest.write_state(directory, state)
        recipient_hash = hashlib.sha256(recipient.casefold().encode()).hexdigest()[:16]
        envelope = {
            "digest_id": pending["digest_id"],
            "idempotency_key": f"fieldnote/{pending['day']}/{recipient_hash}",
            "request": payload,
        }
        digest.write_private(
            directory / "provider.json", json.dumps(envelope, indent=2) + "\n"
        )
    elif pending["status"] == "sending" and pending.get("provider") == "resend":
        age = (now - digest.moment(pending["first_attempt_at"])).total_seconds()
        if age < 0 or age >= RETRY_WINDOW_SECONDS:
            raise ValueError(
                "Unresolved delivery is outside the safe retry window; reconcile the provider receipt before sending"
            )
    else:
        raise ValueError(
            "Unrecognized pending delivery; manual reconciliation required"
        )
    envelope = json.loads((directory / "provider.json").read_text())
    if (
        envelope.get("digest_id") != pending["digest_id"]
        or envelope.get("request") != payload
    ):
        raise ValueError("Retry content changed; refusing to send a second version")
    persist(directory)  # No mail is sent unless the reservation is durable remotely.
    message_id = send(api_key, envelope["request"], envelope["idempotency_key"])
    digest.confirm(directory, pending["digest_id"], message_id)
    persist(directory)
    return {
        "action": "sent",
        "day": pending["day"],
        "job_count": len(pending["job_ids"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    try:
        recipient, sender, api_key = configuration()
        result = run(
            arguments.state_dir.resolve(),
            recipient,
            sender,
            api_key,
            dry_run=arguments.dry_run,
        )
    except (
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
        OSError,
        KeyError,
    ) as error:
        # Never print MIME content, recipient, credentials or private Git output.
        message = (
            str(error)
            if isinstance(error, (ValueError, RuntimeError))
            else "Private outbox or source verification failed; no unsafe retry was attempted"
        )
        print(f"::error::{message}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
