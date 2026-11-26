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

## 6. Lot sizes against the NSE circulars (Haiku 5.5, 24 Nov)

- 2021 (75, then 50 from the July 2021 monthly), May 2024 (25), January 2025 (75 for weeklies) and January 2026 (65)
  match the circulars as quoted by broker bulletins (the NSE PDFs could not be parsed).
- One error: the 30 January 2025 expiry (January 2025 monthly, also that week's weekly) kept the old lot of 25; the
  table gave 75. Four replay trades (entries 24 to 29 Jan 2025) were sized three times too large.
- Fixed in services/algos/nse_lots.py (KEPT_OLD_LOT) with a test. The main rule's replay, same 388 trades, same rule:
  net Rs 1,71,325 realistic (was 1,67,102), Rs 1,10,290 at double cost (was 1,05,861), mean Rs 442, t 2.47 (was 2.39);
  worst trade and deepest fall unchanged. This is a data correction, not a new trial or a tuned result.
- The end-of-day library harness uses the same table, so its draft registration (freeze review 14 Dec) inherits the fix.

## 7. Still open in week 1

- Lot sizes against the NSE circulars.
- Sizing note: size by the largest possible loss (200 points less credit, times lot), not by margin.

## 8. Timing stress runs (run 25 Nov 2026, owner-approved early; settings fixed on 24 Nov)

Script: scripts/algo_backtest/atm200_timing_stress.py (built by GPT-6-Luna; two bugs fixed before use: an exit priced
above the 200-point width was possible, and the combined run let the next-bar fill overwrite intrabar stop fills).
Same 388 trades, same rule; the base reproduces the frozen replay exactly.

| Run | Net, realistic costs | Net, double costs | Per trade | t | Worst trade | Deepest fall |
| --- | --- | --- | --- | --- | --- | --- |
| base (10:15 close, stops on closes) | 1,71,325 | 1,10,290 | 442 | 2.47 | -8,935 | 43,723 |
| a. entry at the 10:15 open | 1,61,657 | 1,00,667 | 417 | 2.32 | -8,589 | 45,227 |
| b. entry one bar later (10:20 close) | 1,69,954 | 1,08,870 | 438 | 2.46 | -9,066 | 43,708 |
| c. stop checked inside each bar | 1,01,539 | 40,459 | 262 | 1.37 | -9,006 | 51,871 |
| d. every exit one bar later | 1,72,851 | 1,11,814 | 445 | 2.49 | -9,111 | 44,206 |
| e. b + c + d together | 1,16,092 | 54,956 | 299 | 1.59 | -9,175 | 51,947 |

Reading:
- Entry and exit timing (a, b, d) move the result by under 6 percent. The rule does not depend on a lucky minute.
- The stop check (c) is the one that matters: checking the stop inside each bar takes about 40 percent of the profit.
  Its test uses the sold call's HIGH minus the bought call's LOW in the same bar, which can be reached at different
  moments, so it is a pessimistic bound: the truth lies between the base and c.
- Owner's rule of 25 Nov (no-go if e loses money at realistic costs): e is +1,16,092, so the rule is NOT marked no-go.
  But at double costs it keeps only Rs 54,956, t 1.59 is far below the register bar, and the deepest fall grows to
  about Rs 52,000 at the replay's lots. Evidence is weaker than the base suggested.

## 9. Failure drills on the separate test bot (25 Nov 2026, 11:00, Sandbox mode)

Bot copy "ATM200-drill" (own files, strikes 300 points out: sold 26200, bought 26400 call, 01 Dec expiry), while the
counted bot held its 25750/25950 spread. Log: log/drill_2026-11-25.log.
- Entry: both legs filled, hedge first; credit 53.2 points. PASS.
- Duplicate entry: "A trade is still recorded (open), so nothing new was placed." PASS.
- Restart: a fresh process picked up the open trade from its state file and reported it held (value 54.0). PASS.
- Emergency exit (flatten): both legs closed; the drill's positions are 0 and 0 in the Sandbox book. PASS.
- Isolation: the counted bot stayed open with its own positions (-65 at 25750, +65 at 25950) untouched. PASS.
Not drilled live (covered only by unit tests): a stale quote, a refused hedge order, a reply lost mid-order.

## 10. Research fixed before running (26 Nov 2026, morning; GPT-6-Astra's open questions)

Run by GLM 5.3 Flash workers on the stored 5-minute bars (October 2024 to October 2026), reviewed with GLM 5.4 advice.
1. The main rule at one constant lot of 65 for every trade (base and the six timing settings), so the deepest fall and
   worst trade are stated in today's money. Descriptive; not a trial.
2. Do the filters earn their keep? The same 200-wide spread entered on EVERY eligible day (no VIX gate, no credit
   floor), with everything else identical, against the gated rule, both at base and combined timing (e), realistic
   and doubled costs. Counted as one trial (361). Reading fixed now: if the ungated version does as well or better at
   e, the gate adds nothing and is noted as such; the frozen rule is not changed either way.
3. Weekly option premium against the move that followed: for each entry day, the ATM straddle (call + put) at the
   10:15 close against the absolute Nifty move from 10:15 to the expiry close. Report the share of days the straddle
   exceeded the move, the average ratio, and the same split by previous VIX below or above its 60-session median.
   Descriptive; not a trial.
