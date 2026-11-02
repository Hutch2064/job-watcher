# Fieldnote Jobs

[![Tests](https://github.com/Hutch2064/job-watcher/actions/workflows/test.yml/badge.svg)](https://github.com/Hutch2064/job-watcher/actions/workflows/test.yml)

A daily job watcher for investment research, portfolio construction, allocation, analytics and investment-facing portfolio solutions. [Open the site](https://hutch2064.github.io/job-watcher/). It watches full public employer ATS boards, not job-board HTML or a third-party aggregator. Roles are global; a title match is a discovery aid, not an assessment of eligibility or job duties.

## Sources

`sources.json` is the authoritative configuration. The initial watchlist has the following public JSON boards; the status on Today shows the result of the latest check. BlackRock includes iShares; Dimensional includes DFA. WisdomTree UK is its UK Lever board, not a claim to cover every WisdomTree location. State Street's board includes the wider company alongside its investment business. The same applies to other diversified firms. An employer can legitimately have zero openings. No board in the initial configuration has been intentionally searched by a term; if an unfiltered board exceeds 5,000, collection fails for that source until a search is configured rather than silently truncating it.

| Employer | ATS |
|---|---|
| BlackRock / iShares | Workday |
| Invesco | Workday |
| Fidelity | Workday |
| Dimensional / DFA | Workday |
| T. Rowe Price | Workday |
| State Street | Workday |
| Vanguard | Workday |
| Apollo | Workday |
| Millennium | Workday |
| Thrivent | Workday |
| Neuberger Berman | Workday |
| AllianceBernstein | Workday |
| Hartford | Workday |
| Northern Trust | Workday |
| TIAA / Nuveen | Workday |
| GMO | Lever |
| Harris / Oakmark | Greenhouse |
| Avantis Investors | Workday |
| Point72 | Greenhouse |
| Bridgewater Associates | Greenhouse |
| Connor, Clark & Lunn | Greenhouse |
| TPG | Greenhouse |
| Jane Street | Greenhouse |
| Betterment | Greenhouse |
| Man Group | Greenhouse |
| AQR | Greenhouse |
| WisdomTree UK | Lever |

See [SOURCE_REVIEW.md](SOURCE_REVIEW.md) for requested brands mapped to the watchlist, investigated sources, and names still requiring individual verification. Those without an accessible, verified JSON board are not represented as watched. This is a practical coverage limit, not a conclusion that they have no openings; employer recruiting sites and access policies change. Some brands share a parent employer's board and cannot be isolated reliably from its other postings. No HTML scraping is used.

## How the pipeline works

At 12:23 UTC daily, GitHub Actions requests every board independently, paginating Workday, validates completeness and unique IDs, writes each successful full JSON response to `data/raw/YYYY-MM-DD/<source>.json.gz`, and records each result. An incomplete, blocked or failed board gets no raw file on that date. On a same-day rerun its previous raw file is replaced or removed; a failed check cannot imply removals. The program rebuilds `data/history.csv` entirely from raw files, in date order, then creates `data/status.json`. It commits the data and opens or updates the dated issue and closes the preceding day's issue. Initial observations per source are not counted as new. On successful later snapshots missing postings are marked removed; reappearing postings retain first seen and reopen. Each source's raw data is kept in the repository. Scheduled runs can be delayed by GitHub.

Run from the repository directory:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python watcher.py build   # reproduce history solely from committed raw files
python watcher.py collect # fetch a new UTC-day snapshot and rebuild status/history
```

The pipeline uses Python's standard library; pytest is the only test dependency. The Workday listing API reports relative posting ages rather than reliable absolute posted dates, so those dates remain blank. Days observed are measured from first sighting, not the employer's original posting date. The Market duration and seven-day share exclude initial-source snapshots; a first observation can still be later than the actual posting date. The removal chart reflects each currently removed posting's latest removal, as the specified one-row history does not retain earlier removal events after reopening. The shortlist is local to the browser and device. The service worker caches the site and last loaded data, using the network first while online; visit the pages online before going offline.

### Title rule

Case-insensitive title matches include portfolio, asset allocation, investment/investing, equity research, fixed income, credit research or analyst, equity analyst, quantitative research or analyst, fund or manager research, ETF, wealth management/advisor, financial planning, investment consulting, OCIO, multi-asset, systematic, risk analytics, or research analyst. Titles containing sales, marketing, accounting/accountant, reconciliation, administrative assistant, recruiter, tax, auditor, software engineer, cybersecurity, compliance, or legal counsel are excluded. This deliberately broad title-only rule can miss relevant jobs or admit unrelated ones; inspect the actual role. All postings are retained regardless of the rule.

## Repository map

| Path | Purpose |
|---|---|
| `watcher.py` | Fetch, validate, normalize, rebuild history, write status. |
| `sources.json` | Employer board configuration. |
| `issues.py` | Create or update the daily change issue and close yesterday's issue. |
| `data/raw/` | Compressed source responses, grouped by UTC date. |
| `data/history.csv`, `data/status.json` | Rebuilt posting history and latest run status. |
| `index.html`, `browse.html`, `market.html` | Today, Browse and Market pages. |
| `common.js`, `today.js`, `browse.js`, `market.js` | Browser loading, interactions and history-derived calculations. |
| `style.css`, `icon.svg`, `icon-192.png`, `icon-512.png` | Shared visual system and app icons. |
| `manifest.webmanifest`, `sw.js` | Installable app metadata and network-first offline cache. |
| `tests/test_watcher.py`, `requirements.txt` | Conversion, title and history tests, and pytest dependency. |
| `.github/workflows/test.yml` | Tests on every push and pull request. |
| `.github/workflows/daily.yml` | Scheduled/manual collector, issue and data commit. |
| `.github/workflows/pages.yml` | GitHub Pages deployment. |
| `.gitignore`, `README.md`, `SOURCE_REVIEW.md`, `SUBMISSION.txt` | Local exclusions, documentation, source review and four-line submission. |
