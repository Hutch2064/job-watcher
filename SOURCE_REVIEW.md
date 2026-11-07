# Source review

The watchlist includes the public ATS JSON boards in `sources.json` and the README. Its broad employer boards contain all jobs the board returns, not just the investment departments. A title match is a prompt to inspect the actual responsibilities, not a finding that an applicant qualifies or that the position is investment decision-making. Initial snapshots from new boards establish a baseline and do not count as new postings.

## Requested firms and source boundaries

BlackRock covers iShares; Dimensional covers DFA; American Century and its Avantis board are tracked separately. WisdomTree's US and UK boards are separate. The watchlist also includes Invesco, Fidelity, T. Rowe Price, State Street, Thrivent, AllianceBernstein, Jane Street, GMO, Oakmark, Global X, VanEck and Calamos. Hartford, BMO, PGIM / Prudential, Manulife and other diversified organizations use company-wide boards, not filters claiming every role is in the asset-management subsidiary. CC&L's quantitative board is distinct from its main board. Board availability, total postings and recruiting systems change.

Global X's public Ashby endpoint responded during this review after a prior 403. The direct UKG JSON listing APIs for VanEck and Calamos responded; they provide brief descriptions but not full job descriptions in the JSON listing. Full job pages are linked for review and are not scraped. Some boards may occasionally reject requests or provide incomplete pages; source status and raw snapshots show whether the latest check succeeded.

## Not yet included

PNC's Workday endpoint reported an apparent 2,000-result cap, with a job-family facet exceeding that number. It is omitted until a complete, stable partition can be verified; a search-only subset is not represented as the complete board. A Sun Life board returned incomplete Workday postings during full-board validation and is not included. Franklin Templeton's public Workday endpoint returned an empty list despite advertised postings, so its completeness remains unverified. Eventide lists positions on its site, but an anonymous, complete ATS JSON board has not been established. Allspring has a careers page whose JSON feed has not been validated.

YieldMax, Tuttle Capital, Overlay Shares, X ETFs, Corgi, Tima, HCM, Schwab, Defiance, Direxion, FT Vest, Nios, Simplify, Rareview, Roundhill, Vega Shares, Logan Capital, IMGP, Bitwise, Morgan Stanley and Goldman Sachs still need individual source validation or provider adapters. This is not a statement that they have no openings. Employer recruiting sites and access policies change. No third-party aggregator or HTML page is treated as an employer JSON board.

## Retired feed

Millennium's configured Workday board repeatedly returned zero while its [current careers site](https://career.mlp.com/careers) lists openings. The unverified board is inactive; its historic raw files remain available for reproducibility. A complete public JSON endpoint for the current careers site has not been validated.
