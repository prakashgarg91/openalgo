# Trial register

Every rule, filter, side, structure, threshold or post-result change that has been tested counts as a trial, so a result that looks good can be judged against how many were tried. Counts are approximate before 1 November 2026 (about 310, taken from the project's own write-ups by the 1 November review) and exact after it. Failures stay on the list.

## Running count

| Family | Trials | Result |
| --- | --- | --- |
| Zen-style spread variants (150+ option spreads, mandate searches) | about 150 | no edge after costs |
| Zen side rules (36 cells) and the three-rule forward test | 36 + 3 | 34 of 36 lost in the last third |
| Daily real-price grid | 48 | 33 of 48 lost |
| ETF rules (search of 23) | 23 | the winner is mostly equity and gold exposure |
| ETF shadow ledgers (ideas 1 to 3 and 12 candidates) | 15 | none beat a plain hold at the same exposure on 15 years |
| Regime-gated spread cells | 12 | none qualified |
| Intraday momentum pairs | 12 | 0 verified |
| Linkage, chain, horizon, range, premium studies | many (counted in their write-ups) | no direction predictor |
| Structures S1 to S4 (and narrow variants) | about 6 | S3n narrow earned under both cost scenarios, failed its statistical gate; registered for a forward test |
| Six registered ideas | 6 | not yet run forward |
| **Total at 1 November 2026** | **about 310** | |

## Entries since then

| No. | Date | Registration | Kind | Status |
| --- | --- | --- | --- | --- |
| 311 | 1 Nov 2026 | [c1-registration.md](c1-registration.md), month-end ETF window | forward shadow ledger | running from the first month-end in the data |

## Rules for new entries

1. One new idea a month at most. A replay on stored history can only reject an idea. It never promotes one, because every holdout in the two-year option data has been looked at at least once.
2. An idea is registered (rule, costs, gates, stop, trial number) before anything is run, and goes forward in sandbox mode or as a shadow ledger. Only forward days count.
3. A pass bar is the significance 0.025 divided by the running trial count, rounded as written in its registration.
4. Three discarded ideas from the 1 November review (long strangle priced by a volatility forecast, expiry-day iron butterfly, equity-gold snapback) are not registered. If one is ever registered it takes the next number.
