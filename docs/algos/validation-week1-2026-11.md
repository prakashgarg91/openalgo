# Validation week 1 findings (24 November 2026 onward)

Part of GPT-6-Astra's 4-week validation (docs/algos/astra-review-2026-11-23.md). Read-only checks; nothing tuned, nothing re-run as a new result.

## 1. Replay reproduction and 20-trade hand check (Haiku 5.5, 24 Nov)

- The replay reproduces: 388 trades, net Rs 1,67,102 realistic, Rs 1,05,861 at double cost, mean Rs 431, t 2.39,
  worst trade Rs -8,935, deepest fall Rs 43,723. Exits: target 146, stop 9, time 233. Costs about Rs 61,000 of
  Rs 2,28,343 gross.
- 20 trades (seed 20261124, including best and worst) recomputed by hand from the raw candles: no mismatch in credit,
  exit reason, exit value or gross. Lots 25, 65 and 75 by expiry date (from nse_lots.py; not yet checked against the circulars).
- The VIX gate held (largest previous VIX in the trade set 19.88); the credit floor never bound (smallest 30.45 points).

## 2. Timing found by the check (to be measured, not fixed by retuning)

- Bars are labelled by their START time. The replay enters on the CLOSE of the 10:15 bar, which is the 10:20 price,
  and decides and fills on that same close. The replay's own text says "open of the 10:15 bar". The live Sandbox bot
  enters at 10:16. So the replay is about 4 minutes later than the bot, and its decision and fill share one price.
- Stops and targets are checked on 5-minute bar CLOSES, and the exit is booked at that close. A real stop fills during
  the bar, and the decision can only act at the next bar. Close-based stops flatter the stop results.
- The time exit is booked at the 15:00 bar close, which is the 15:05 price; the bot exits at 15:00.

Consequence: these are execution gaps between the replay and the live bot. Week 3's stress test measures them with
settings fixed now (below). They are measurements of the same frozen rule, not new variants, and no setting is chosen
from their results.

## 3. Week-3 sensitivity runs, fixed before any is run

a. Entry at the 10:15 bar OPEN (the 10:15 price) instead of its close.
b. Entry at the 10:20 bar close (decide on the 10:15 close, fill one bar later).
c. Stops and targets checked on bar highs and lows (the worse side for the position), filled at the stop level.
d. Every exit filled one bar later than its decision.
e. All of the above together, at realistic and at double costs.
Report each beside the base result. The base result stays the frozen reference; none of these replaces it.

## 4. Cost table against official rates (Haiku 5.5, 24 Nov)

- Brokerage Rs 20 an order, SEBI fee, stamp duty, GST, and STT from October 2024 (0.10 percent, 0.15 percent from
  1 April 2026) all MATCH. The exchange charge in code (0.0345 percent) matches no official figure: 0.0495 percent
  before October 2024, 0.03503 percent to February 2026, 0.03553 percent from March 2026. Before October 2024 STT was
  0.0625 percent, so the code overstates STT and understates the exchange charge there; the two nearly cancel.
- Worked example, one lot of a 160/87 call spread at April 2026 rates: our charges Rs 132.07 a round trip; the
  official rates differ by under Rs 1 in every period checked. No difference moves a one-lot trade by Rs 10 or more.
- STT on exercise is not modelled, but the rule always exits by 15:00 on the next session, before settlement, so no
  leg is exercised. Immaterial for this rule.
- Caveats: the NSE circular PDF could not be parsed (figure from the Upstox page); some rates rest on search snippets.
- Verdict: costs are not a source of error in the replay.

## 5. Sizing note (24 Nov)

The largest possible loss of one lot is the spread width less the credit, times the lot: (200 - credit) x 65.

| Credit (points) | Largest loss of one lot | Share of Rs 1,00,000 |
| --- | --- | --- |
| 100 | Rs 6,500 | 6.5 percent |
| 76.6 (the 18 Nov Sandbox trade) | Rs 8,021 | 8.0 percent |
| 60 | Rs 9,100 | 9.1 percent |
| 30 (smallest seen in the replay) | Rs 11,050 | 11.1 percent |

- The stop (spread value at 2.5 times the credit) sits close to the full width for most credits (191.5 against 200
  at 76.6 points), and a gap through the stop goes to the full width; so the stop does not make a loss much smaller
  than the largest loss. The replay's worst single trade was Rs -8,935.
- One lot therefore risks about 6 to 11 percent of Rs 1,00,000 per trade. A common rule of thumb for a single
  trade is 1 to 2 percent; on that rule one lot fits an account of about Rs 4 lakh to Rs 11 lakh. This is
  information for the owner's decision, not a change to any limit.
- The pilot pause at a cumulative loss of Rs 10,000 can be reached by one full loss plus one small loss.
- Margin (about Rs 40,700 plus the bought premium) is what Upstox blocks; it is not the risk. The risk is the
  largest loss above.

## 6. Still open in week 1

- Lot sizes against the NSE circulars.
- Sizing note: size by the largest possible loss (200 points less credit, times lot), not by margin.
