from datetime import datetime, timedelta, timezone
import io
import json
from urllib.error import HTTPError, URLError

import pytest

import cloud_digest
import digest

DAY = "2026-11-09"
NOW = datetime(2026, 11, 9, 18, tzinfo=timezone.utc)
RECIPIENT = "applicant@example.com"
SENDER = "Fieldnote <jobs@example.com>"
MESSAGE_ID = "e196015b-5f0e-4565-9ae3-591c135fe898"


def update():
    return {
        "commit": "abc",
        "workflow_run_id": 124,
        "status": {
            "run_time": DAY + "T17:00:00Z",
            "sources": [{"id": "a", "ok": True, "last_success": DAY}],
        },
        "rows": [
            {
                "posting_id": f"a:{index}",
                "source": "a",
                "employer": "Example Investments",
                "title": f"Portfolio Construction Analyst {index}",
                "location": "Dallas, TX",
                "url": f"https://example.com/jobs/{index}",
                "status": "open",
                "experience": "early",
                "experience_reason": "0-2 years of experience mentioned",
                "duty_excerpt": "Analyze investment portfolios and model asset allocation.",
                "first_seen": DAY,
                "last_seen": DAY,
            }
            for index in range(7)
        ],
    }


@pytest.fixture
def outbox(tmp_path):
    digest.write_state(
        tmp_path,
        {
            "sent_dates": {"2026-11-08": {"message_id": "old-gmail-id"}},
            "sent_job_ids": ["a:0"],
            "pending": None,
        },
    )
    return tmp_path


def execute(
    outbox, persist=lambda directory: None, send=lambda *args: MESSAGE_ID, **options
):
    return cloud_digest.run(
        outbox,
        RECIPIENT,
        SENDER,
        "test-key",
        now=options.pop("now", NOW),
        fetch_update=lambda **kwargs: (update(), ""),
        persist=persist,
        send=send,
        **options,
    )


def test_sends_five_with_durable_reservation_and_then_receipt(outbox):
    events = []

    def persist(directory):
        state = digest.read_state(directory)
        events.append("reserved" if state["pending"] else "confirmed")
        if state["pending"]:
            assert state["pending"]["status"] == "sending"
            assert (directory / "provider.json").exists()

    def send(key, payload, idempotency_key):
        events.append("send")
        assert events == ["reserved", "send"]
        assert payload["to"] == [RECIPIENT]
        assert not {"cc", "bcc"} & payload.keys()
        assert "Five roles" in payload["html"]
        assert payload["html"].count("View role &amp; apply") == 5
        assert idempotency_key.startswith(f"fieldnote/{DAY}/")
        return MESSAGE_ID

    result = execute(outbox, persist=persist, send=send)
    assert result == {"action": "sent", "day": DAY, "job_count": 5}
    assert events == ["reserved", "send", "confirmed"]
    state = digest.read_state(outbox)
    assert state["sent_dates"]["2026-11-08"]["message_id"] == "old-gmail-id"
    assert state["sent_dates"][DAY]["message_id"] == MESSAGE_ID
    assert state["sent_dates"][DAY]["provider"] == "resend"
    assert state["sent_job_ids"] == [f"a:{index}" for index in range(6)]
    assert state["pending"] is None
    # Even a redundant same-day trigger cannot send again.
    assert (
        execute(outbox, send=lambda *args: pytest.fail("duplicate send"))["action"]
        == "skip"
    )


def test_missing_private_history_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="history is missing"):
        execute(tmp_path, send=lambda *args: pytest.fail("must not send"))


def test_failed_reservation_push_never_sends(outbox):
    def failed_push(directory):
        raise RuntimeError("private push failed")

    with pytest.raises(RuntimeError, match="push failed"):
        execute(
            outbox,
            persist=failed_push,
            send=lambda *args: pytest.fail("must persist before sending"),
        )


def test_ambiguous_send_retries_identical_payload_and_key(outbox):
    calls = []

    def uncertain_send(key, payload, idempotency_key):
        calls.append((payload, idempotency_key))
        raise RuntimeError("unknown provider result")

    with pytest.raises(RuntimeError, match="unknown"):
        execute(outbox, send=uncertain_send)
    assert digest.read_state(outbox)["pending"]["status"] == "sending"

    def retry(key, payload, idempotency_key):
        assert (payload, idempotency_key) == calls[0]
        return MESSAGE_ID

    execute(outbox, now=NOW + timedelta(hours=1), send=retry)
    assert digest.read_state(outbox)["pending"] is None


def test_confirmation_push_failure_can_reconcile_from_remote_sending_state(outbox):
    remote_snapshot = {}
    calls = []

    def persist(directory):
        if digest.read_state(directory)["pending"]:
            remote_snapshot.update(
                {
                    name: (directory / name).read_text()
                    for name in cloud_digest.PRIVATE_FILES
                    if (directory / name).is_file()
                }
            )
        else:
            raise RuntimeError("receipt push failed")

    def send(key, payload, idempotency_key):
        calls.append(idempotency_key)
        return MESSAGE_ID  # Resend returns the original ID for the same key.

    with pytest.raises(RuntimeError, match="receipt push failed"):
        execute(outbox, persist=persist, send=send)
    for name, text in remote_snapshot.items():
        (outbox / name).write_text(text)
    execute(outbox, now=NOW + timedelta(hours=1), send=send)
    assert calls[0] == calls[1]
    assert digest.read_state(outbox)["sent_dates"][DAY]["message_id"] == MESSAGE_ID


def test_expired_uncertain_attempt_is_never_resent(outbox):
    def uncertain(*args):
        raise RuntimeError("uncertain")

    with pytest.raises(RuntimeError):
        execute(outbox, send=uncertain)
    with pytest.raises(ValueError, match="safe retry window"):
        execute(
            outbox,
            now=NOW + timedelta(hours=23),
            send=lambda *args: pytest.fail("unsafe resend"),
        )
    assert digest.read_state(outbox)["pending"]["status"] == "sending"


def test_changed_envelope_cannot_reuse_an_idempotency_key(outbox):
    with pytest.raises(RuntimeError):
        execute(
            outbox, send=lambda *args: (_ for _ in ()).throw(RuntimeError("uncertain"))
        )
    with pytest.raises(ValueError, match="Retry content changed"):
        cloud_digest.run(
            outbox,
            RECIPIENT,
            "Different <other@example.com>",
            "key",
            now=NOW,
            send=lambda *args: pytest.fail("changed request"),
        )


def test_rechecks_location_and_recipient_before_calling_provider(outbox):
    digest.prepare(outbox, RECIPIENT, update())
    selection_path = outbox / "selection.json"
    selection = json.loads(selection_path.read_text())
    selection["jobs"][0]["location"] = "New York, NY"
    selection_path.write_text(json.dumps(selection))
    with pytest.raises(ValueError, match="remote-or-Texas"):
        execute(outbox, send=lambda *args: pytest.fail("ineligible job"))
    with pytest.raises(ValueError, match="reservation"):
        cloud_digest.run(outbox, "different@example.com", SENDER, "key", now=NOW)


def test_dry_run_does_not_modify_state_or_contact_provider(outbox):
    before = (outbox / "state.json").read_text()
    result = execute(
        outbox,
        dry_run=True,
        persist=lambda *args: pytest.fail("dry run wrote history"),
        send=lambda *args: pytest.fail("dry run sent mail"),
    )
    assert result == {"action": "dry-run", "day": DAY, "job_count": 5}
    assert (outbox / "state.json").read_text() == before
    assert not (outbox / "provider.json").exists()


def test_provider_request_keeps_both_mime_alternatives_and_idempotency_header(
    monkeypatch,
):
    received = []

    def respond(request, timeout):
        received.append(request)
        assert timeout == 30
        return io.BytesIO(json.dumps({"id": MESSAGE_ID}).encode())

    monkeypatch.setattr(cloud_digest.urllib.request, "urlopen", respond)
    payload = {
        "from": SENDER,
        "to": [RECIPIENT],
        "subject": "A subject",
        "html": "<p>HTML</p>",
        "text": "Plain",
    }
    assert cloud_digest.send_resend("test-key", payload, "one-day") == MESSAGE_ID
    assert received[0].get_header("Idempotency-key") == "one-day"
    assert json.loads(received[0].data) == payload


@pytest.mark.parametrize(
    "failure",
    [
        URLError("private address should not appear"),
        HTTPError(
            "https://api.resend.com/emails", 429, "private address", {}, io.BytesIO()
        ),
    ],
    ids=["network", "http"],
)
def test_provider_errors_keep_sensitive_details_out_of_logs(monkeypatch, failure):
    def failed(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cloud_digest.urllib.request, "urlopen", failed)
    with pytest.raises(RuntimeError) as error:
        cloud_digest.send_resend("test-key", {}, "one-day")
    assert "private address" not in str(error.value)
