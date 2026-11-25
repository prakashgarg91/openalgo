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
| none | 1 Nov 2026 | [nse-eod-registration.md](nse-eod-registration.md), NSE end-of-day Nifty futures and options 2015 to 2026 | data only, no strategy, no trial | registered; download follows |
| 312 to 319 | run 2 Nov 2026 (registered for 1 Dec, brought forward by the owner) | [eight-structure-screen-registration.md](eight-structure-screen-registration.md), eight structures on NSE end-of-day data | rejection screen, run once | all eight rejected, no survivor: [results](eight-structure-screen-results.md) |
| 320 | 2 Nov 2026 (owner lifted the monthly slot for it) | [vol-scaled-etf-registration.md](vol-scaled-etf-registration.md), volatility-scaled equity and gold | rejection screen on 15 years of ETF closes, run once | rejected, fails five of six gates (loses to its matched hold in 13 of 14 years): [results](vol-scaled-etf-results.md) |
| 321 | 6 Nov 2026 (frozen; register entry due January 2027) | [zen-follow-registration.md](zen-follow-registration.md), Zen call spreads only | forward shadow ledger on Zen's own advices | running; 6 unseen call spreads so far, inconclusive |
| 322 to 325 (approximate) | 6 Nov 2026 | [zen-structure-replay-2026-11.md](zen-structure-replay-2026-11.md), fixed Zen-shaped 400-wide spread: put and call side, with and without the VIX gate | exploratory screen on seen 5-minute candles, rules written before the run | call spreads earned in both periods; a screen only, nothing promoted |
| 326 to 334 (approximate; recorded late, on 18 Nov 2026, with the owner's yes) | 17 Nov 2026 | 200-wide call spread looks made in memory by the director model on the same seen candles: a far-strike version (withdrawn: about Rs 60 a trade, lost at doubled costs), an at-the-money version with and without the VIX gate at two cost levels and two lot conventions, and a 50-point credit floor (dropped: it lowered the result). See [sandbox-bot.md](sandbox-bot.md) and `scripts/algo_backtest/atm200_replay_check.py` | exploratory looks on seen data, not tests; nothing was written to disk at the time | best cell t = 2.39 (388 trades, net Rs 1,67,102, historical lots); runs forward in Sandbox mode only; not registered |
| 335 to 359 (approximate; the owner waived the one-a-month rule for it on 19 Nov 2026) | 19 Nov 2026 | [vendor-decider-registration-2026-11.md](vendor-decider-registration-2026-11.md), a monthly decider over a fixed pool of 24 vendor algos by calm or nervous condition | walk-forward test on vendor-reported daily results, frozen then run once | FAIL: walk-forward t = -0.10; it lost while following all 24 equally earned a little; see [vendor-decider-results-2026-11.md](vendor-decider-results-2026-11.md) |
| 360 | 25 Nov 2026 | [narrow-spread-registration-2026-11.md](narrow-spread-registration-2026-11.md), ATM 100-wide call credit spread, frozen 25 Nov (owner), one descriptive replay on the stored 5-minute bars with the six timing settings | Base 388 trades, net Rs 65,570 realistic (Rs 3,064 doubled), t 1.69; combined timing run (e) net Rs -1,23,412, t -2.68. Registered stop sign met (e loses at realistic costs): RETIRED, the forward shadow ledger never starts. The first run stopped at a VIX-file column error before any result was seen; fixed in 74ba1b54a and run once. Trial count now about 360. |

## Rules for new entries

1. One new idea a month at most. A replay on stored history can only reject an idea. It never promotes one, because every holdout in the two-year option data has been looked at at least once.
2. An idea is registered (rule, costs, gates, stop, trial number) before anything is run, and goes forward in sandbox mode or as a shadow ledger. Only forward days count.
3. A pass bar is the significance 0.025 divided by the running trial count, rounded as written in its registration.
4. Three discarded ideas from the 1 November review (long strangle priced by a volatility forecast, expiry-day iron butterfly, equity-gold snapback) are not registered. If one is ever registered it takes the next number.
