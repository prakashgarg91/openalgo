# Vendor algo decider: pre-registration (written 19 November 2026, before any result of the pool was read)

STATUS: FROZEN (by the owner's word "Freeze and run" on 19 November 2026; nothing had been run and no pool result had been read at this commit).

**Frozen. The single run follows this commit.** The owner freezes it by saying so; the line that marks the freeze is added then, in its own commit, and the run script refuses until that commit exists and nothing has changed since.

POOL_SHA256: 371077a495db3480ecc030fc80a13352dd17f4870445f0a9ea95a6482b4a039c

## The idea, in plain words

The owner's idea: copy what Stratzy's algos do in different conditions and let a decider choose the right algo for the time. What can be tested with public figures is narrower: Stratzy shows each algo's daily result, not its rule. So the test asks one question: **each month, choosing one algo per market condition from a fixed pool, using only that pool's own past results, would the choice have beaten simply following all of them?**

## Data

- Daily results of Stratzy algos as shown by the vendor, in percent points of each algo's own maximum allocation, collected on 14 October 2026 and read in place from the trading-rex-ai folder. They are the vendor's reported figures. They exclude our costs and the subscription, and they are not audited.
- Only days on or after an algo's live-since date are used. Earlier days are vendor backtest and are never used, for choosing or for judging.

## The pool (fixed on 19 November 2026 without reading any result)

From 405 algos: defined risk, at least 100 days of results, minimum capital Rs 1,00,000 or less; then the 12 Credit Spread and the 12 Option Buying algos with the most days of results, ties by name. The list is `research/stratzy_candidates/pool_24.csv` in the private data repository; its fingerprint is the POOL_SHA256 line above.

## The market condition

Each day is **calm** or **nervous**, known before the open: nervous when the previous session's India VIX close is above the median of the 60 closes before it, otherwise calm. This replaced fixed volatility bands after a count of dates only showed 385 low, 40 mid and 16 high sessions in the window, which cannot be learned from. By the same count the new split gives 252 calm and 186 nervous sessions since January 2025.

## How the choice is made

- At each month start, for each condition: the pool algo with the highest average daily result on its live days in that condition over the previous 6 months.
- An algo needs at least 15 such days. A condition is traded only when at least 6 algos qualify and the best average is above zero. Otherwise the decider sits out that condition for the month.
- The look-back was set by a count of dates only: 4 months left a condition empty in 7 of 15 months; 6 months covers 266 of 294 sessions; longer adds nothing.
- Judged months: August 2025 to October 2026 (the data ends 13 October). Earlier months are warm-up and history only.

## What is reported

- View A, best in hindsight: the best algo per condition over the whole period. In-sample, not evidence.
- View B, walk-forward: the only result judged.
- Two benchmarks over the same judged months: following all 24 equally each day, and the single algo with the best warm-up average held throughout.

## Pass lines, fixed now

A pass needs all of: at least 80 walk-forward days (fewer is "inconclusive"); walk-forward t statistic of at least 2.0; both halves positive; walk-forward total above the equal-weight total; walk-forward total above the warm-up-best total. Anything else is a fail.

## Trials and honesty notes

- Trials: 24 pool algos and one selector, 25 in all; the running count goes from about 334 to about 359. The owner waived the one-new-idea-a-month rule for this test on 19 November 2026.
- A t of 2.0 is far below the register's bar (0.025 divided by the count, about 3.8 standard errors). A pass is a reason to check forward, not proof.
- What was already seen: Zen's own daily results (one of the 24) were studied earlier; the weekly public listing reads of 6 and 17 November showed 3-month, 6-month and 1-year return figures for many of these algos; another agent's regime studies used this collection. The pool was chosen by day counts and capital only, and this session has not read the daily results of the other 23.
- Survivorship: the collection holds algos listed on 14 October 2026. Algos the vendor removed earlier are missing, which flatters every figure, including the benchmarks.
- Many of the 24 went live only in 2025 or 2026, and the whole judged period is 15 months.

## What each outcome permits

- Pass: a forward check on fresh results (after 13 October 2026) with the picks frozen in advance, under its own note. Never real money by itself; following a vendor algo also needs its subscription and capital.
- Fail or inconclusive: the idea is recorded as tested and not shown. Nothing is tuned and re-run; a changed rule is a new trial.

## Code

`services/algos/vendor_decider.py` (rules and pass lines), `scripts/algo_backtest/vendor_decider_run.py` (the single guarded run), built on `services/algos/portfolio_select.py`, `portfolio_report.py` and `portfolio_wf.py`. Tested on made-up data only: on pure noise the hindsight view looks good while the walk-forward view sits near zero.
