# Narrower call-only structures: results (1 November 2026, run once)

Rules: [structures-narrow-registration.md](structures-narrow-registration.md), committed before either variant was replayed. Code: `services/algos/condor.py` (width parameter), `scripts/algo_backtest/structures_study.py --narrow`. Tables: private data repository, `research/structures_narrow/`. Same 108 expiries, 513 sessions, the first 342 for selection and the last 171 held out (already seen twice). Realistic costs unless stated; "at twice" doubles them. One lot, rupees.

## Verdict

**Neither variant passed. S1n (daily call spread, 100 wide) was not even a candidate: it fails at twice the costs in selection. S3n (weekly call spread, 100 wide) cleared every gate except the statistical one: its drawdown is inside the Rs 20,000 limit for the first time, but a lower bound on the mean daily result is still below zero at the level corrected for six structures. It is not promoted by this registration.**

## Selection period (342 sessions)

| | Trades | Before costs | Earlier cost model | Realistic | At twice | Worst drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S1n daily call spread, 100 wide | 194 | +44,525 | -24,674 | +12,588 | -19,349 | 30,458 |
| S3n weekly call spread, 100 wide | 68 | +46,590 | +21,541 | +35,380 | +24,171 | 15,013 |

Candidates (at least 40 trades and positive at twice the realistic costs): S3n only.

## Last third (171 sessions)

| | Trades | Before costs | Earlier model | Realistic | At twice | Worst drawdown | Worst day |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1n | 88 | +28,683 | -2,496 | +14,477 | +271 | 18,082 | -6,971 |
| S3n | 30 | +40,362 | +29,600 | +35,530 | +30,697 | 13,425 | -6,916 |

S3n against the registered gates: at least 20 trades (met), positive at realistic costs (met), positive at twice (met), drawdown within Rs 20,000 (**met**, 13,425 and 15,013 in selection), no day losing more than Rs 20,000 (met), bootstrap lower bound above zero at the six-structure level (**failed**: the bound is about -44 a day).

## What it says

1. **A 100-point wing fits the loss limit and keeps the profit.** S3n earns about Rs 35,000 in each period under realistic costs, Rs 24,000 to Rs 31,000 at twice the costs, with a worst drawdown of Rs 13,000 to Rs 15,000. At 250 points the same structure earned more and drew down about Rs 27,000 to Rs 32,000. The profit per rupee of risk is similar; the limit is now respected.
2. **The statistical test is the remaining gap, and a short sample can't close it.** The weekly structure makes about one trade a week: 30 in the last third. Its daily results are lumpy, and the corrected bound stays below zero. More weeks, not a better rule, is what would change that.
3. **The daily version does not hold up.** S1n earns Rs 12,600 realistic in selection but is negative at twice the costs, and only barely positive at twice in the last third (Rs 271). With a 100-point wing the credit is small, so costs and the assumed slippage take a large share of it.
4. **It is still a short-call structure.** By trailing market (the Nifty's return over the 20 sessions before entry), S3n's realistic net was +40,423 after non-falling stretches and -5,043 after falling ones in selection, and +15,856 and +19,673 in the last third. It profits when the Nifty does not rally hard; a sharp rally is its risk.

## What it means for the next step

- S3n is the one structure in this whole project that meets the loss limit, is positive under realistic and doubled costs in both periods, and fails only on the statistical bar. That makes it a reasonable candidate for a forward shadow ledger on new days in sandbox mode, which is the only clean test left, and which needs about six months to say anything. It is a hypothesis, not a finding: it was reached after trying six structures on a window seen several times.
- No other width will be tried on this data.
- The measured bid and ask will decide whether the 0.15-point slippage assumption is right, and a narrow spread is the most sensitive to it.

## Trials counted

These two, with the first four structures, the 12 spread cells, the 36 earlier Zen cells, the three forward rules and the research families before them.

## Limits

Candle fills with no bid and ask; one window in which the Nifty fell overall; 30 weekly trades in the last third; the held-out third was seen twice before this test and the 250-point results were known when 100 was chosen.

## Correction (2 November 2026)

The lot size used in this replay was wrong for the October to December 2024 weeks (75 where the lot was 25). The study was re-run as a correction; the verdict is unchanged and the corrected tables are in [lot-size-correction.md](lot-size-correction.md).

