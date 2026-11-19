# Vendor algo decider: result of the single run (19 November 2026)

Registration: [vendor-decider-registration-2026-11.md](vendor-decider-registration-2026-11.md), frozen at commit `b1e2a4a65`. Run once, right after the freeze. Full printed output: private data repository, `research/vendor_decider/run_2026-11-19.txt`. Figures are percent points of each algo's own maximum allocation, as reported by the vendor, without our costs.

## Verdict: FAIL

The first pass line failed: the walk-forward t statistic is -0.10, below 2.0.

| | Total | Per day | t | Days | Both halves positive |
| --- | --- | --- | --- | --- | --- |
| Decider, walk-forward (the judged view) | -15.8 | -0.08 | -0.10 | 194 | no |
| Follow all 24 equally | +49.8 | +0.17 | 0.92 | 293 | yes |
| Best warm-up algo held (IV-Imbalance Credit Spread Overnight) | +213.4 | +1.14 | 2.71 | 187 | yes |
| Best in hindsight (in-sample, not evidence) | +175.9 | +1.74 | 2.67 | 101 | yes |

## What it shows

- Choosing last half-year's best algo per condition did not earn: it lost a little, while simply following everything earned a little. The hindsight view looks good (+176) on the same data, which is the gap the noise test predicted: picking winners after the fact always looks profitable.
- The decider changed its pick often (Index Sniper for five months, then eight different algos), and 17 of 26 picks were credit spreads. Chasing the recent best algo did not carry forward.
- One algo held throughout (the warm-up best) did well, but that is a single algo over 15 months chosen from 24, in vendor figures, so it is an observation and not a result: it was not the registered hypothesis and its t of 2.7 is far below the register's bar.
- The vendor's whole pool earned only +0.17 percent points a day before our costs and the subscription.

## What follows

- The idea "a decider that picks the right vendor algo for the condition" is recorded as tested and not shown. Nothing is tuned and re-run; a changed rule would be a new trial.
- Trial count: 25 added (rows 335 to 359, approximate).
- Following a single vendor algo remains what the Zen follow ledger already tests forward.
