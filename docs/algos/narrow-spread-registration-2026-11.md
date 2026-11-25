# Pre-registration: ATM 100-wide call credit spread (frozen 25 November 2026)

STATUS: FROZEN

Approved by the owner on 25 Nov 2026 ("Yes, freeze it"). This file and its code (services/algos/atm100_rule.py,
scripts/algo_backtest/atm100_replay.py, scripts/algo_backtest/atm100_shadow_ledger.py, test/test_atm100.py) are frozen
by the commit that adds this line. A defect found later may be fixed, but the re-run counts as a new trial.

## Why

The owner's pilot limits (25 Nov: daily loss budget Rs 5,000, skip any trade whose largest loss does not fit) rule
out one lot of the 200-wide spread (largest loss Rs 6,500 to 9,100). A 100-wide spread's largest loss is
(100 - credit) x 65, about Rs 2,900 to 4,200 at credits of 35 to 55 points, which fits.

## The rule (identical to the frozen 200-wide rule except the width and the credit floor)

- Nearest weekly Nifty expiry 1 to 6 calendar days away, with a session before it.
- Enter at 10:15: sell the ATM call (spot rounded to 50, Python round), buy the call 100 points higher.
- Skip when the previous session's India VIX close is 20 or more. Skip when the credit is 3 points or less
  (the 200-wide floor of 5 points, scaled by width and rounded down; fixed now, not searched).
- Exit: target when the spread value is 31 percent of the credit or less; stop at 2.5 times the credit or more;
  otherwise at 15:00 on the next session. One lot (lot by expiry from services/algos/nse_lots.py), one position.
- Costs: services/algos/eod_screen.leg_cost, realistic and doubled.

## The honest limit of past data

Our 5-minute option bars cover October 2024 to October 2026, the same window on which the 200-wide rule was found.
The 100-wide spread's legs are the same sold call plus a nearer bought call, so its past result is strongly tied to
the 200-wide result already seen. A past replay therefore cannot be independent evidence. It is run once only as a
DESCRIPTION, with the five timing settings of 24 Nov (base, a, b, c, d, e), and the real test is forward.

## Steps and pass lines (fixed now)

1. Replay once on the past data (one counted trial): report trades, net at realistic and doubled costs, t, worst
   trade, deepest fall, and the five timing settings. It is NOT a pass or fail. It is a stop sign only if the
   combined timing run (e) loses money at realistic costs; then the idea is retired and step 2 never starts.
2. Forward SHADOW ledger from 26 Nov 2026 (the first trading day after the freeze), computed each evening by
   scripts/algo_backtest/atm100_shadow_ledger.py from the one-minute candles the nightly capture stores: entry on the
   10:15 one-minute close, exits on one-minute closes, costs by leg_cost, one position at a time, written to
   research/atm100_forward/ledger.csv in the data repo. Change made before the freeze, with the reason: a second
   Sandbox bot would sell the same at-the-money call as the counted 200-wide bot, and Sandbox positions are pooled by
   contract, so the two bots would block or tangle each other. The shadow ledger places no order and cannot interfere. Judged after 60 completed trades
   (about four months) at realistic costs: pass needs net positive, t of at least 2.0, worst day better than
   Rs -5,000, deepest fall under Rs 10,000, and every entry inside the pilot limits. Anything else is a fail.
3. A pass makes the 100-wide spread eligible for the one-lot manual pilot under the 25 Nov limits. Never Live from
   the replay.

## What it will not do

Search widths, targets, stops, entry times or gates; replace the 200-wide rule or its Sandbox bot; place a real order.

## Cost and risk

Cost: one worker job (done) and a few seconds each evening for the ledger. Risk: low; the
forward ledger is slow (about four months to 60 trades) and cannot be hurried honestly.

## Result (25 November 2026): RETIRED

One run (trial 360) after the VIX-column fix (74ba1b54a; the first attempt stopped before any result was seen):

| Run | Net, realistic | Net, doubled | Per trade | t | Worst trade | Deepest fall |
| --- | --- | --- | --- | --- | --- | --- |
| base | 65,570 | 3,064 | 169 | 1.69 | -4,609 | 24,863 |
| a. entry at 10:15 open | 58,984 | -3,497 | 152 | 1.51 | -4,673 | 25,329 |
| b. entry one bar later | 68,719 | 6,193 | 177 | 1.78 | -4,571 | 23,572 |
| c. stop inside each bar | -1,18,273 | -1,80,970 | -305 | -2.59 | -4,593 | 1,24,803 |
| d. exit one bar later | 69,279 | 6,779 | 179 | 1.77 | -4,491 | 24,994 |
| e. b + c + d | -1,23,412 | -1,86,023 | -318 | -2.68 | -4,632 | 1,26,907 |

The registered stop sign is met: the combined run (e) loses money at realistic costs, so the idea is retired and the
forward shadow ledger does not start. The intrabar-stop setting (c) is a pessimistic bound (sold high minus bought
low within a bar), and it bites a narrower spread harder because its stop sits only about 2.5 credits from entry;
that is noted, not used to rescue the idea. Even without it, the base keeps only Rs 3,064 at double costs.
