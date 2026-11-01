# Forward shadow test of the weekly call spread (S3n): registered 1 November 2026, before any counted entry

Why: [structures-narrow-results.md](structures-narrow-results.md) found one structure that fits the Rs 20,000 loss limit and stays positive under realistic and doubled costs in both periods, and fails only the statistical bound because it has about 30 weekly trades in the last third. Every other result in this project was reached on a window that has been seen several times, so the only clean test left is new days. This page fixes that test before the first counted entry. It is a shadow ledger computed from stored candles in sandbox mode. No order is placed anywhere, and nothing here is an expected profit.

## The two ledgers

- **L1, S3n (the one under test).** One weekly Nifty call spread: sell the call at the money, buy the call 100 points above it. Entry at 10:15 on the second trading session before the weekly expiry session, at the open of the 10:15 one-minute candle. Held to the last one-minute candle of the expiry session (15:29), taking its close. No stop, no target, no reversal. One lot, using the lot size in force on the entry date.
- **L2, S3 at 250 points (reference only).** The same entry, with the long call 250 points above. It cannot be promoted. It is there to show whether the width matters on new days.

The previous forward test ([forward-test-registration.md](forward-test-registration.md), side rules A, B and C on a daily entry) is unchanged and independent. This registration does not retire it; the trader may stop its A and B ledgers, which earned nothing before costs in the earlier tests.

## Data and start date

The nightly capture ([option-capture.md](option-capture.md)): one-minute candles of the nearest weekly Nifty expiry, 16 strikes either side of the money plus the day's range, Nifty one-minute index candles and India VIX daily. The first counted entry is the one for the weekly expiry of **Tuesday 10 November 2026**, entered on Friday 6 November. The expiry of 3 November (entered on 30 October) is excluded because its entry day was already in the past when this page was written. A session counts only if the capture saved it.

## Filters and cost scenarios

The filters of every earlier test: no entry if the previous session's India VIX closed at 20 or higher, or if the Nifty at the entry time is 1 percent or more below the previous close. If either leg has no candle at the entry minute, or the expiry session is only partly stored (its last candle earlier than 15:29), the week is recorded as not counted, with the reason, and is never filled in afterwards. Every result is reported under the earlier cost model and the retail-realistic scenario. When about 60 sessions of measured bid and ask exist ([bid-ask-snapshots.md](bid-ask-snapshots.md)), the measured half-spread replaces the 0.15-point slippage as one further scenario, registered before it is applied. The pass decision is made on realistic costs and on twice them.

## The end of the test and the pass rule, fixed now

The test ends at the earlier of 26 completed trades in L1 (about six months of weekly entries) and 31 May 2027. Nothing is decided before the end except the stopping rule below and repairs of data problems that change no trading decision. A repair that changes a decision restarts the count under a new version.

L1 passes only if all of these hold at the end:

- At least 26 completed trades (fewer is "inconclusive", not a pass).
- Net profit above zero under realistic costs and above zero at twice the costs.
- Worst drawdown, marked to market each session, no more than Rs 20,000, and no single day losing more than Rs 20,000.
- A one-sided 97.5 percent lower bound above zero for the mean net result per completed trade, by a moving-block bootstrap (block of 3 trades, 10,000 draws, a fixed seed).
- Net profit still above zero after the single best trade is removed.

## Stopping rule

If L1's cumulative realistic net falls to Rs -20,000 at any time, the test stops and is recorded as a fail: that is the loss budget of the account. It is not reopened.

## Reported at the end whatever the result

Every counted and every not-counted week with its reason; both ledgers under both scenarios; the Nifty's own move over the test period and the split of the result by the sign of the Nifty's return over the 20 sessions before each entry (a short call does best when the Nifty does not rally, and a test that happens to run in a falling or flat market proves little about a rising one); the number of trials this test belongs to (L1 and L2 here, the six structures before them, the 12 spread cells, the 36 earlier Zen cells, the three forward side rules and the research families).

## What a pass and a fail mean

A pass: S3n may be considered for a further, longer sandbox run and for a conversation about real money, which needs a different registration, a static-IP broker setup and your own decision. It is not an expected profit. A fail or an inconclusive result: the call-only family is dropped. In every case the data used by this test is not used to choose a width or any other parameter.

## Open points settled in code before the first entry (and not changed afterwards)

- The weekly expiry list comes from the stored contract names; a holiday-shifted expiry is whatever the stored symbol says.
- The entry session is counted in captured sessions, so a missing capture day moves nothing and removes that week.
- Weekly entries never block each other: each is held to its own expiry, and two can be open at once only if two expiries overlap, which the weekly cycle does not produce.
- The replay for one-minute data passes the last-candle time 15:29, not the 15:25 used for five-minute bars; the earlier defect where a stored session ended before the expected last candle and left a position open for ever is excluded by treating such a week as "not counted" and never as "still open".

## Limits

Candle fills with no bid and ask; about 26 trades is a small sample, so even a pass leaves large uncertainty; one half-year may be a falling, rising or flat Nifty and says nothing about the others; a short call has a tail in a sharp rally, capped here by the 100-point wing; the nightly capture must run on both the entry day and the expiry day of each week.

## Build status

Built and tested on 1 November 2026, before any counted entry. `services/algos/forward_weekly.py` holds the two ledgers, the report and the stop and pass rule; `scripts/algo_backtest/run_forward_s3n.py` runs them from the stored one-minute candles after each nightly capture (it is in `capture_option_candles.cmd` after the older forward test) and writes `db/forward_s3n/report.json` and `trades_L1.csv`, `trades_L2.csv`. The weekly replay in `services/algos/condor.py` gained three arguments with defaults that leave every earlier result unchanged (re-running the 100-point study reproduces the stored numbers exactly): the last-candle time (15:29), a refusal when either leg has no candle at the entry minute, and the first counted expiry.

How the code treats the cases above:

- A week entered whose expiry session is not stored yet is shown as open and marked to the last stored candle. It becomes a completed trade, or a recorded not-counted week, once the expiry session is stored.
- The entry session of an open week is taken as two weekdays before its expiry; once the expiry is stored it is taken as two stored sessions before it. A holiday or a missing capture day can therefore move a stored week's entry by one session: every trade in the report carries the calendar days between entry and expiry (4 for a Friday entry and a Tuesday expiry), so a shifted week is visible, and a repair that changes a decision restarts the count under a new version.
- The bootstrap runs over completed trades (block of 3, 10,000 draws, seed 20261101, one-sided 97.5 percent), not over days as in the earlier studies. The stopping rule looks at the lowest marked-to-market equity as well as the realised total.
- The pass decision is made on the retail-realistic cost scenario (Rs 20 per order, STT, GST, stamp duty, 0.15-point slippage); the earlier cost model is reported beside it.
