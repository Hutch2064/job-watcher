"""Exercise cloud delivery against Resend's documented simulator, never a person."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cloud_digest
import digest

# This address is Resend's delivery simulator. It cannot be set by workflow input.
SIMULATOR = "delivered+fieldnote@resend.dev"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    arguments = parser.parse_args()
    history = arguments.state_dir.resolve()
    original_state = (history / "state.json").read_text()
    cloud_digest.load_delivery_state(history)
    _, sender, api_key = cloud_digest.configuration()
    update, reason = digest.remote_update()
    if not update:
        raise RuntimeError(reason)
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        prepared = digest.prepare(directory, SIMULATOR, update)
        payload = cloud_digest.provider_payload(directory, SIMULATOR, sender)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        key = (
            "fieldnote-delivery-check/"
            + hashlib.sha256(serialized.encode()).hexdigest()
        )
        first_id = cloud_digest.send_resend(api_key, payload, key)
        repeated_id = cloud_digest.send_resend(api_key, payload, key)
        if first_id != repeated_id:
            raise RuntimeError("Provider idempotency check returned different receipts")
        receipt = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "message_id": first_id,
            "job_count": prepared["job_count"],
            "source_commit": update["commit"],
            "idempotency_verified": True,
        }
        digest.write_private(
            history / "provider-check.json", json.dumps(receipt, indent=2) + "\n"
        )
    if (history / "state.json").read_text() != original_state:
        raise RuntimeError("Delivery verification changed production receipts")
    cloud_digest.persist_outbox(history)
    print(
        json.dumps(
            {
                "action": "provider-verified",
                "job_count": receipt["job_count"],
                "idempotency_verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()
