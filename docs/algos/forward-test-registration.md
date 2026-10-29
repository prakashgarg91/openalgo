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

## Open points to settle in code before the first trade (not tuned afterwards)

- Whether the target near 10 points means profit taken or remaining value.
- Which weekly expiry is used on expiry day.
- Whether a reversal keeps the original next-day exit.
- How the gap and VIX filters treat a reversal and a position held overnight.
- Fill model: the capture holds candles, not bid and ask, so results stay provisional. If a stop and a target fall in one bar, the worse order is assumed.

## Limits

- An overnight position can gap through the Rs 20,000 daily cap. The spread limits the terminal loss (worst published trade on one lot was about Rs 13,300) but the cap is not guaranteed.
- A sample without rising, falling and flat periods cannot show that a rule works in all weather.
- Nothing has been built yet. This page is the registration, not a result.
