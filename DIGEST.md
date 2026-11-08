# Personal daily shortlist

The private digest selects up to two unseen, open early-career roles after a
successful **Daily job watch** update. It includes direct employer application
links, the source location, the experience evidence, a short duties excerpt and
an explainable score. It sends fewer than two rather than filling the email
with unqualified matches. When none qualify, it sends a short no-match update.

## Ranking

The score is a discovery ranking, not an eligibility decision or a hiring
probability. It has four components:

| Component | Maximum | Evidence |
|---|---:|---|
| Career fit | 50 | Portfolio construction and allocation lead, followed by portfolio research, investment research and investment decision support. |
| Experience | 35 | Internships and a stated minimum of zero or one year lead; a minimum of two years scores slightly lower. |
| Duties | 10 | An analytical responsibility connected to portfolios, investments, securities, funds, trading or investment performance. |
| Recency | 5 | When the tracker first observed the opening; this is not necessarily its original posting date. |

Only roles with an early-career signal are eligible. Senior titles, roles
classified as experienced, MBA/PhD-specific title tracks without known
eligibility, invalid application links, stale observations and inactive sources
are excluded. Generic infrastructure and platform-support titles receive a
lower career-fit score. The minimum score is 65. The email is limited to **remote roles or roles with a
Texas location**. Texas can be one of several locations. Exact city-only labels
for Austin, Dallas, Houston, San Antonio and Fort Worth are recognized; a
contrary state qualifier (such as Austin, MN) is not treated as Texas. Remote roles explicitly
restricted to another state or country and hybrid roles outside Texas are
excluded; a generic remote label is accepted, subject to employer confirmation
of location and work-authorization requirements. Unclear locations are excluded.
This restriction applies to the email shortlist; Browse retains the full watchlist.

A successful source check on the update's UTC date is required. The script
reads status and history at one GitHub commit and verifies that the collection
timestamp falls within a completed, successful daily workflow. It waits if the
workflow is still running or failed. Snapshots older than 36 hours are not used.

## Delivery

The connected Gmail account is used by a scheduled task in this chat. The task
checks for completion every 15 minutes, sends after a successful update is
detected, and sends at most once per UTC update day. It is not an immediate
GitHub email hook. The computer and desktop app must be running for this local
scheduled task; a provider credential would be required for a separate delivery
worker that runs while the computer is off.

Recipient configuration, MIME content and message receipts live in the ignored
`.digest-local/` directory, with private file permissions. None is deployed to
GitHub Pages. The Python program prepares content but never sends email on its
own. The scheduled task uses the connected Gmail sending tool and records its
message ID only after a successful response.

Before every send the task searches Sent mail for the exact dated subject. A
pending send with an unknown outcome is reconciled against Gmail; it is never
blindly resent. Previously delivered posting IDs are excluded from later
shortlists. The backup daily collection does not produce a second email for
the same UTC date. Email has both HTML and plain-text MIME parts, uses inline
styling, and has no remote fonts, tracking pixel or external image dependency.

## Commands

```bash
# Configure the recipient locally, fetch one verified remote snapshot and reserve it.
python3 digest.py prepare --recipient YOUR_EMAIL

# Later runs reuse the private recipient config.
python3 digest.py prepare

# Mark a reservation as sending immediately before the Gmail call.
python3 digest.py claim --digest-id ID

# After Gmail returns a message ID, persist the receipt.
python3 digest.py confirm --digest-id ID --message-id GMAIL_MESSAGE_ID

# A never-sent reservation can be discarded. Sending attempts cannot.
python3 digest.py discard --digest-id ID
```

`prepare` reports `ready`, `reconcile`, or `skip`. It avoids re-downloading the
history after that update date has been sent. `tests/test_digest.py` covers
ranking, stale/senior exclusions, source escaping and duplicate protection.
The browser test renders a source-backed email preview and checks mobile width.
