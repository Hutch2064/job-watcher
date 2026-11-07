"""Generate a source-backed email preview for browser layout checks in CI."""

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import digest

status = json.loads((ROOT / "data/status.json").read_text())
with (ROOT / "data/history.csv").open(newline="", encoding="utf-8") as stream:
    jobs = digest.select_jobs(list(csv.DictReader(stream)), status)
_, html, _ = digest.email_content(jobs, status["run_time"][:10], status["run_time"])
(ROOT / "email-preview.html").write_text(html)
