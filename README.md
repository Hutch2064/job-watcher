# Fieldnote Jobs

[![Tests](https://github.com/Hutch2064/job-watcher/actions/workflows/test.yml/badge.svg)](https://github.com/Hutch2064/job-watcher/actions/workflows/test.yml)

A daily job watcher for investment research, portfolio construction, allocation, analytics and investment-facing portfolio solutions. [Open the site](https://hutch2064.github.io/job-watcher/). It watches full public employer ATS boards, not job-board HTML or a third-party aggregator. Roles are global; a title match is a discovery aid, not an assessment of eligibility or job duties.


```text
Public ATS JSON → daily raw snapshots → deterministic history and status
                                      ↘ GitHub issue and Pages site
```

## Sources

`sources.json` is the authoritative configuration. The watchlist has the following public JSON boards; the status on Today shows the result of the latest check. BlackRock includes iShares; Dimensional includes DFA. WisdomTree UK is its UK Lever board, not a claim to cover every WisdomTree location. State Street's board includes the wider company alongside its investment business. The same applies to other diversified firms. An employer can legitimately have zero openings. No configured board is filtered by a search term. A board exceeding 5,000 postings fails validation rather than being truncated. Workday responses reporting exactly 2,000 are also rejected because that can be a capped result.

| Employer / board | ATS |
|---|---|
| BlackRock | Workday |
| Invesco | Workday |
| Fidelity | Workday |
| Dimensional | Workday |
| T. Rowe Price | Workday |
| State Street | Workday |
| Vanguard | Workday |
| Apollo | Workday |
| Millennium | Workday (inactive; see source review) |
| Point72 | Greenhouse |
| Bridgewater Associates | Greenhouse |
| Connor, Clark & Lunn | Greenhouse |
| TPG | Greenhouse |
| Jane Street | Greenhouse |
| Betterment | Greenhouse |
| Man Group | Greenhouse |
| AQR | Greenhouse |
| WisdomTree UK | Lever |
| Thrivent | Workday |
| Neuberger Berman | Workday |
| AllianceBernstein | Workday |
| Hartford | Workday |
| Northern Trust | Workday |
| TIAA / Nuveen | Workday |
| GMO | Lever |
| Harris / Oakmark | Greenhouse |
| Avantis Investors | Workday |
| Capital Group | Workday |
| PIMCO | Workday |
| Wellington Management | Workday |
| Russell Investments | Workday |
| Fiera Capital | Workday |
| PGIM / Prudential | Workday |
| Texas Permanent School Fund | Workday |
| Ontario Teachers Pension Plan | Workday |
| Ares Management | Workday |
| Manulife | Workday |
| Cambridge Associates | Workday |
| BMO | Workday |
| Athora | Workday |
| Jupiter Asset Management | Workday |
| New York State Teachers Retirement System | Workday |
| CAAT Pension Plan | Workday |
| Brookfield | Workday |
| ICONIQ | Greenhouse |
| Vise | Greenhouse |
| Forteus / Numeus | Greenhouse |
| Choreo | Greenhouse |
| Star Mountain Capital | Greenhouse |
| CAIS | Greenhouse |
| CC&L Quantitative | Greenhouse |
| Galvanize | Greenhouse |
| Mercer Advisors | Greenhouse |
| iCapital | Greenhouse |
| WisdomTree US | Lever |
| EP Wealth Advisors | Lever |
| Wealthfront | Lever |
| Global X ETFs | Ashby |
| Range | Ashby |
| Compound Planning | Ashby |
| Calamos Investments | UKG Pro Recruiting |
| VanEck | UKG Pro Recruiting |
| American Century Investments | Workday |

See [SOURCE_REVIEW.md](SOURCE_REVIEW.md) for requested brands mapped to the watchlist, investigated sources, and names still requiring individual verification. Those without an accessible, verified JSON board are not represented as watched. This is a practical coverage limit, not a conclusion that they have no openings; employer recruiting sites and access policies change. Some brands share a parent employer's board and cannot be isolated reliably from its other postings. No HTML scraping is used.

## How the pipeline works

At 12:23 and 20:23 UTC daily, GitHub Actions requests every board independently, paginating Workday and UKG, validates completeness and unique IDs, retries failed or changing boards up to three times, writes each successful full JSON response to `data/raw/YYYY-MM-DD/<source>.json.gz`, and records each result. An incomplete, blocked or failed board gets no raw file on that date. On a same-day rerun, a successful raw file is replaced, while a failed retry preserves the earlier successful snapshot and reports the latest error. The program rebuilds `data/history.csv` entirely from raw files, in date order, then creates `data/status.json`. It commits the data and opens or updates the dated issue and closes older dated Job Watcher issues. The daily workflow explicitly dispatches the test workflow after its bot commit, because GitHub does not trigger push workflows for that commit. Initial observations per source are not counted as new. On successful later snapshots missing postings are marked removed; reappearing postings retain first seen and reopen. Each source's raw data is kept in the repository. Scheduled runs can be delayed by GitHub.

Run from the repository directory:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python watcher.py build   # reproduce history solely from committed raw files
python watcher.py collect # fetch a new UTC-day snapshot and rebuild status/history
```

The pipeline uses Python's standard library; pytest is the only test dependency. The Workday listing API reports relative posting ages rather than reliable absolute posted dates, so those dates remain blank. Days observed are measured from first sighting, not the employer's original posting date. The Market duration and seven-day share exclude initial-source snapshots; a first observation can still be later than the actual posting date. The removal chart reflects each currently removed posting's latest removal, as the specified one-row history does not retain earlier removal events after reopening. Browse refreshes its data when the page regains focus and every minute while visible, preserving the current filters. Data requests bypass the browser HTTP cache when online; offline access uses the last cached snapshot. The shortlist is local to the browser and device. The service worker caches the site and last loaded data, using the network first while online; visit the pages online before going offline.

### Experience filter

Browse defaults to early-career signals plus postings that need review. Titles containing intern or internship are early-career signals, including joined forms such as SummerIntern; internal and international are not treated as internships. Summer and program titles are also early-career signals unless the title is senior or the description mentions a minimum of three or more years. Other explicit senior titles and postings that mention a minimum of three or more years are set aside. Ranges starting below three years remain in the early-career group. Clearly preferred experience is not treated as a minimum. The rule is a heuristic: it can miss or misread requirements, alternate qualifications and seniority; open the original job description before making a decision. A title alone does not prove an analyst or associate position is entry level, so postings without a recognizable requirement are labeled “Needs review.” You can select a category or show every level.

Greenhouse, Lever and Ashby descriptions come from their board JSON. UKG supplies only a brief description in its JSON listing; no HTML job descriptions are scraped. Browse displays a short source-derived duty excerpt when one is available, not an automated judgment that the job fits. If a Workday listing lacks a title, the collector recovers it from the public job-detail JSON; the unmodified listing and recovered title are both stored in the raw snapshot, and unrecoverable listings fail validation. For relevant Workday titles, the collector also requests the public job-detail JSON and stores the description alongside its board snapshot. A detail request that fails leaves the posting's experience unknown, without making the source fail or marking jobs removed. Historical raw snapshots created before this enrichment do not contain Workday details and remain reproducible. The latest available snapshot determines the assessment in the history; the raw data remains the source of truth.

### Title rule

Case-insensitive title matches include portfolio, asset allocation, investment/investing, equity and credit research or analyst, quantitative research or analyst, fund or manager research, ETF, wealth management/advisor, financial planning, investment consulting, OCIO, multi-asset, systematic, risk analytics/analyst/analysis/reporting, performance analyst/analysis/attribution/reporting, due diligence, investment or trading operations, operations analyst/associate/specialist, trade support, corporate actions, fund accounting or administration, asset management, and research analyst/associate. Titles containing sales, marketing, administrative assistant, recruiter, tax, auditor, software engineer, cybersecurity, or legal counsel are excluded. Accounting, reconciliations and compliance are no longer blanket exclusions: the responsibilities can have substantive analytical content. This deliberately broad title-only rule can miss relevant jobs or admit unrelated ones; inspect the actual role. All postings are retained regardless of the rule.

### Cover-letter evidence

For title-matching Greenhouse jobs, the collector requests each job's public JSON application-form questions, preserving the response in the raw snapshot. A required or optional cover-letter field is labeled from its actual form metadata. An explicit required or optional statement in a job description is also reported with its source; contradictory evidence is flagged for review. “No field found” means a complete form definition contained no recognizable cover-letter field; it does not mean the application has no written questions. Conflicting or ambiguous description/form wording is “Check details.” Sources without accessible form metadata, failed form lookups and older snapshots are “Unknown” unless the job description provides evidence: an explicit requirement or optional statement is labeled accordingly, and an ambiguous mention says “Check details.” Never infer that a cover letter is optional from missing information. The filter can show optional fields and forms with no field together. A form may change after the daily check, and the actual application always controls.

Lever's public postings API does not expose custom application questions; the public Ashby job-board API, Workday listing and UKG listing do not provide the complete application form used here. No application HTML, candidate information, credentials or submissions are collected.

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

Raw snapshots grow over time (approximately 3 MB per day in the initial week). For longer-term operation, older raw files could move to versioned release assets while retaining a reproducible archive. Millennium’s zero-result Workday feed is inactive pending validation of its current careers feed.
