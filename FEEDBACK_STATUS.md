# Changes made from the original review

This checklist distinguishes implemented changes from partial improvements and
ideas that remain. It covers the original data, site, design, repository and
feature feedback, plus the personal email digest added afterward.

## Data and daily operation

| Feedback | Current result |
|---|---|
| Failed feeds looked current | Today shows each source's last successful date, error or warning; Market labels stale employers. Failed checks preserve the last observation. |
| Northern Trust throttling | Collected outside the board thread pool, with one detail worker, slower request spacing and Retry-After handling. |
| Excessive Workday requests | Shared request pacing and server-requested cooldowns; rate-limited optional details stop without discarding a complete job list. |
| One malformed BMO posting failed the whole board | A missing external path is skipped and logged. Pagination and duplicate checks still validate the rest of the board. |
| Empty or sharply reduced feed could remove everything | Counts below half the previous good snapshot are flagged suspect. The last good data is retained; a documented override supports verified real changes. |
| Same-day failed retry could destroy a good snapshot | A later failed attempt preserves the earlier successful snapshot for that day. |
| Millennium repeatedly returned zero | Its unverified Workday feed is inactive, documented and retained as history. A current replacement feed is still unverified. |
| Vise's Greenhouse feed stopped working | Added its current Ashby feed as a new baseline. The retired Greenhouse source remains inactive history; older records may overlap. |
| Only one scheduled attempt | Added a second daily schedule, documented delay limitations and bounded future collections to 45 minutes. |
| Greenhouse offset dates | Converted to UTC dates through the shared date helper. |
| Workday dates and multiple locations | Detail JSON supplies posting dates and actual location names where available; explicit remote signals are retained. Enrichment is best effort. |
| Location aliases | Common state/country aliases are normalized, and Market counts each listed city once per posting. This is not a complete geographic alias service. |
| Removed/unknown source config broke rebuilds | Unknown raw sources are skipped with a warning; intentionally retired configured sources remain available for rebuilding history. |
| Older dated GitHub issues stayed open | All older daily Job Watcher issues are closed, including after missed days. |
| Concurrent main-branch changes could reject the bot push | Daily commits pull with rebase before pushing. |
| Raw archive growth | README explains archive growth and a possible release-asset retention approach. No historical raw files were deleted. |

## Site and user experience

| Feedback | Current result |
|---|---|
| Offline failed after first visit | Data and app assets are cached on installation/first load; an offline notice identifies the saved data. A clean-context browser test covers first-visit offline reload. |
| Today buried useful jobs | Compact briefing leads with new role matches in the early-career/review group, with full new/removed lists behind an expandable section. |
| Source health was at the bottom | Source health appears before the full change lists, with unavailable sources first and reasons visible. |
| Huge location dropdown | Replaced by a searchable location input with suggestions. |
| Browse controls pushed jobs too far down | Shorter heading, primary controls and a More filters panel. |
| Shortlist depended on unrelated filters | Its own view ignores the normal search, role, experience and other filters. |
| Removed saved jobs disappeared | Saved removed postings remain in the shortlist and are marked removed. |
| No reset or active-filter summary | Clear all and individually removable filter chips. |
| Search depended on word order | Each search word is matched independently. |
| Cover-letter clutter | Required/optional badges appear only when there is evidence; no Unknown badge on every card. Three filter choices replace the overlapping set. |
| Repeated history downloads | Status is checked first; history is reused when run_time has not changed. The every-minute full-download loop was removed. |
| Market time charts | New and removed observations run left to right as columns. Role counts have their own labeled scale. |
| Employer chart too long | Top 15 plus All others. |
| Empty seven-day bars and duration language | Seven-day bars are omitted until eligible history exists. Singular/plural handling and the short-history caveat are included. |
| Market scope and accessibility | All postings / Your role scope switch; table views for the daily additions, removals, employer and location charts. Not every chart has a table yet. |
| Keyboard/screen-reader feedback | Star focus is retained on toggle, mode buttons expose aria-pressed, labels update, result counts have a live region, a skip link is present and decorative external arrows are hidden. |
| Control readability and touch use | Larger form fields, clearer control borders/focus states, inherited button fonts and responsive layouts. This is not a formal accessibility certification. |
| Card density and saving feedback | Compact badges, expandable duties, star beside title, saved-card treatment, shortlist count and remove-with-Undo feedback. |
| Motion and visual hierarchy | Hover/pressed/selected states, short transitions, reduced-motion support, distinct new/removed/warning/error/shortlist color roles and clearer surfaces/type. |
| Header and phone navigation | Sticky header with active-page indicator; bottom navigation on phones with safe-area spacing. |
| Loading/error/empty states | Fixed-size loading placeholders, common retry block, explanatory empty search/shortlist states. The placeholders are static rather than animated shimmer. |
| Date/number formatting | Thousands separators, shorter displayed timestamps, relative posting dates and tabular figures for key numbers. A relative Updated N hours ago clock is not implemented. |
| Shared filtered views | Browse controls are stored in the URL. |
| Installed-app polish | Manifest ID, Apple touch icon, maskable declaration, shortcuts, matched header/theme color, refresh action and conditional Install app button. Manifest screenshots are not added. |
| Font dependence while offline | Self-hosted fonts, licenses and service-worker font caching. |

## Repository, documentation and tests

| Feedback | Current result |
|---|---|
| Minified-looking frontend | HTML, CSS and JavaScript are formatted as readable source. Browse has named filter functions. |
| Dense Python | Python is formatted and helper functions/tests were added. The five ATS adapters have not yet been separated into their own modules. |
| Untested frontend and issue report | Python tests cover source/history/safety rules and issue text. Node tests cover frontend helpers. GitHub runs browser, shortlist persistence, phone width, offline and email-layout checks. |
| Publishing the entire repository | Pages receives site assets and public data only; raw archives, Python code and tests are excluded. |
| Titles could mention GitHub accounts | Issue text neutralizes @ mentions in source-provided titles/employer/location text. |
| Repeated localStorage parsing per card | The saved-ID set is read once per render and passed into card rendering. |
| README presentation | Added an actual tested site screenshot and a simple pipeline diagram; updated schedules, source notes, retention notes and digest documentation. |
| Leftover dictated note and table typo | Removed the spoken-name note and fixed the Oakmark spacing. |

## Features integrated from the ideas section

- A personal daily briefing and date-based new-since-last-visit count; app badge where supported.
- A local application tracker: Saved, Applied, Interviewing, Closed, notes, saved date, CSV export and print styling.
- Source-health panel, recent saved-observation strip and labeled GitHub anomaly alerts.
- A new-role RSS feed with no sending credential requirement.
- A plain-language Methods page linked from the site and README.
- A professional personal HTML/plain-text email with direct application links,
  explainable ranking and duplicate-send safeguards. It waits for a successful
  daily workflow, checking every 15 minutes through the local app.
- The email is now restricted to remote roles or Texas locations, including
  multi-location postings that offer Texas. Explicitly incompatible remote
  geography and hybrid roles outside Texas are excluded. The public Browse
  watchlist keeps all locations.

## Remaining limitations and optional ideas

- Millennium's current replacement JSON feed has not been verified.
- Retired Vise records are preserved as last-known history and can overlap the current feed.
- The email checker requires the computer and app to be running. A separate
  provider credential is needed for direct cloud delivery while the computer is off.
- The ATS-specific Python module split remains unfinished.
- Employer sparklines, historical source-failure markers on charts, slimmer
  page-specific datasets, a light theme, animated number changes and manifest
  screenshots are not implemented.
- Source-history squares represent saved observations, not a complete historical
  log of every failed attempt. The current error and repeated-failure count are available.
- Source details, cover-letter forms, location rules and applicant eligibility
  can change; the employer's current application controls.
- The assignment's successful-date requirement must accumulate naturally; no
  dates are fabricated to satisfy it.
