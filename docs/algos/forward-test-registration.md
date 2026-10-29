# Forward test of three side rules, registered before any trade (29 October 2026)

Why this page exists: Zen's exits reproduce (correlation +0.91 with its 204 published trades) but how it picks put or call does not. Six side rules we wrote lost money in the last third of the data (34 of 36 pre-registered cells), and the two that did not only sold call spreads into a falling Nifty. This page fixes the next test before any day of it is seen. See [stratzy-comparison.md](stratzy-comparison.md) and [option-capture.md](option-capture.md).

Nothing here is an expected profit. The design was drafted with GPT-6.1 Sol in the OpenAlgo agent (discussion only, no tool called), checked and adopted by the owner's request. The numbers below are chosen thresholds, not estimates.

## What runs

Sandbox mode only, three separate sandbox accounts of Rs 1,00,000, one lot, Nifty weekly credit spread. All three share one frozen entry and exit machine, taken from the replay that reproduced Zen's exits: at the money, 400 points wide, entry at 10:15, one position at a time, stop 43.8 points over the credit then reverse, target near 10 points, exit at 15:00 the next session, no entry when India VIX is 20 or higher or after a 1 percent gap down.

Side rule, using Nifty spot candles that are complete at 10:15. P is the last complete one-minute close, O the session open, V the previous close. Equal takes the "otherwise" branch. Missing data means no entry, and the reason is recorded.

| Rule | Sell a put spread when | Otherwise | Role |
| --- | --- | --- | --- |
| A, continuation | P is above O and above V | call spread | Candidate |
| B, opening-move fade | P is below or equal to O | call spread | Candidate |
| C, always calls | never | call spread every day | Control, cannot be promoted |

## Gates, per candidate, at the registered end

The end is 252 trading sessions. 8 to 12 weeks of captured days are a shakedown only and decide nothing. An entry and the reversals it causes count as one episode.

- At least 100 completed episodes.
- Net profit at least Rs 10,000 after costs, and still positive with twice the cost deduction.
- Maximum drawdown no more than Rs 20,000, marked to market, not closed trades alone.
- No day losing more than Rs 20,000.
- One-sided 97.5 percent lower bound above zero for mean net daily result, by a moving-block bootstrap with a block of 5 sessions.
- The same bound above zero for the paired daily difference against rule C.

All gates must hold. Too few episodes at the end is "inconclusive", not a pass. If neither candidate passes, stop trying to rebuild Zen's hidden side rule from this data.

## Trials to report

All three rules, including the control, and the 36 earlier cells. Any change to a rule, filter, exit, expiry choice or cost assumption is a new variant, is listed, and a repair that changes a trading decision restarts the sample under a new version.

## Open points, settled in code before the first trade (version 2026-10-29-v1)

- Target near 10 points means the spread's remaining value at a candle close is 10 points or less, not profit taken.
- Expiry: the nearest weekly on or after the day, so on expiry day it is that day. A position still held at the expiry close leaves there.
- A reversal keeps the same exits as an entry (15:00 the next session, stop, target). It reverses only if the stop was hit the same day at or before 14:30, up to 3 times.
- The VIX and gap filters are read once, at the first entry of a day, from the previous session's India VIX close and from P against the previous close. They do not apply to a reversal. A position held overnight blocks the next day's entry.
- A missing number (no 09:15 or 10:14 index candle, no previous close, no VIX) means no entry that day, and the reason is counted. The previous session is the latest earlier date with index candles through 15:29; a day whose capture stopped early, or a VIX close missing for that date, is not used, so a missed evening can never feed a stale value into a decision.
- The strike is the price at 10:14 rounded to the nearest 50 (an exact half rounds to the even hundred, as in the Zen replay).
- Drawdown and the Rs 20,000 daily cap are marked to market using the worst spread value reached inside each session a position is held, not only the closing value. A day with no stored candle for a held position carries its last value forward.
- A position on an expiry day that is only partly stored is treated as still open, not closed at a mid-session candle.
- The report says "not due yet" until 252 sessions are stored; `all_gates` and a pass can only appear at that point.
- No-trade days count as zero in the daily series used by the statistical gates.
- Fills are candle prices at the open of the entry candle, with the stop taken at the pessimistic spread high plus 2 points. Costs are the conservative model already used in the Zen replay. A candle that could hold both a stop and a target takes the stop. Results stay provisional until checked against real bid and ask.

## Where it runs

Nothing here places an order, in sandbox mode or any other. One Nifty sandbox account cannot hold three independent books, so each rule is a separate shadow ledger replayed from the stored candles, which also makes every night's result repeatable. The code is `services/algos/forward_shadow.py` (rules, replay, gates; no database) and `forward_shadow_data.py` (reads Historify). `scripts/algo_backtest/run_forward_shadow.py` prints where the test stands and writes `db/forward_shadow/`; the Windows capture task runs it after each evening's capture. The capture now also saves the Nifty index minutes and India VIX days the rules need.

## Limits

- An overnight position can gap through the Rs 20,000 daily cap. The spread limits the terminal loss (worst published trade on one lot was about Rs 13,300) but the cap is not guaranteed.
- A sample without rising, falling and flat periods cannot show that a rule works in all weather.
- The runner is built and tested on constructed days and on the first stored day (29 October 2026, one session). That is a working check, not a result. Any change to the code that alters a decision starts a new version and a new sample.
