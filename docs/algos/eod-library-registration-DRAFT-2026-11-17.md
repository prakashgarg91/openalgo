# DRAFT pre-registration: end-of-day library test (17 November 2026)

Written by Fable 5.2 (director), saved by Sonnet 5.5. NOT registered, NOT frozen, no trial counted, nothing run. Registration is binding and needs the owner's word. After the owner approves, the document and the code are frozen by one commit and no change is allowed.

## Data

NSE end-of-day Nifty weekly options in `openalgo-data/nse_fo_eod`, April 2021 to October 2026. February 2019 to March 2021 stays untouched.

## What "seen" means

Earlier screens already looked at this window, and the library below was written by people who know what worked in it. Walk-forward protects the choosing, not the library. A pass here is a reason to test forward and is not proof.

## (a) Library: five algos, one lot, every value fixed

Common terms: nearest weekly expiry 1 to 6 calendar days away; enter at today's close, exit at the next session's close; ATM is the Nifty close rounded to the nearest 50; every leg must have traded on both days or the trade is dropped and counted; no stops or targets (end-of-day data cannot see them).

| Algo | Legs |
| --- | --- |
| A1 call credit spread | Sell ATM call, buy +200 |
| A2 put credit spread | Sell ATM put, buy -200 |
| A3 iron condor | Sell +200 call, buy +400; sell -200 put, buy -400 |
| A4 call debit spread | Buy ATM call, sell +200 |
| A5 put debit spread | Buy ATM put, sell -200 |

"No trade" is always available.

## (b) Cells

Volatility band from the frozen model in `services/algos/regime_gate.py` using the previous session's VIX close and range: groups 1-2 low, 3 mid, 4-5 high. If the entry or exit day is in the committed list `docs/algos/eod_library_events.json` (national events only: Union Budget, RBI policy decision days, Lok Sabha counting; each category is used only when complete), no trade. Mid and high are labelled but are forced no-trade: only the low band is learned (director's ruling of 17 Nov 2026 on counts alone: 853 low, 160 mid, 79 high usable trades per algo).

## (c) Selection and valuation

- Selection at each month-end, per cell: the algo with the highest net rupees per trade among trades that exited in the trailing 12 months; at least 40 trades and a positive mean, otherwise no trade. Picks apply to the next month.
- Warm-up April 2021 to March 2022; evaluation April 2022 to October 2026. All trades dated by exit day.
- Costs: `services/algos/eod_screen.leg_cost` for every leg, at realistic and doubled (the doubled run re-selects on doubled costs), lots from `services/algos/nse_lots.py`.
- Expiry-day exit: each leg at its intrinsic value from the settlement price. The spread clamp between zero and the width is implemented and tested but not applied, because per-leg intrinsic values already lie inside it. A listed expiry with no rows on its own date is kept only when its last rows are 1 or 2 calendar days before it (7 of 299 labels; eligible sessions 1,104 to 1,098).

## (d) Views and pass and fail lines, fixed now

View A (hindsight): best algo per cell over the whole window; in-sample, not evidence. View B (walk-forward): the only result judged.

A pass needs all of these on view B at realistic costs: net t of at least 2.0; both halves positive; worst day better than a Rs 10,000 loss; drawdown under Rs 20,000; beats the benchmark (the algo with the best net per trade on low-cell trades exiting in the warm-up, then held on every low-cell trade with no monthly gate; zero if none is positive); zero days over the Rs 27,000 cap; still net positive at doubled costs. Anything else is a fail.

## (e) Trials

Adds six (five algos, one selector): about 334 to 340, counting the exploratory looks of 6 and 17 November now written in TRIAL_REGISTER.md (rows 322 to 334, approximate). A t of 2.0 is well below the register bar of about 3.8. Only a forward ledger can meet that bar.

## (f) Haiku jobs, in order (Sonnet verifies each; Fable reviews)

1. Counts only, no profit computed: sessions, expiries, usable legs and trades per cell per algo. Accept if at least 40 trades exist in each TRADEABLE cell (low only) in 90 percent of evaluation months; otherwise stop and return to the director. Done on 17 Nov 2026: low 100 percent (mid 27 percent and high 15 percent, hence forced no-trade).
2. Valuation functions: settlement clamp, lots by date and costs, tested on made-up rows.
3. Wire into the existing harness (`services/algos/portfolio_*.py`): the noise test and planted-edge test must pass, and exit-day dating must be tested.
4. Freeze: record the code and document commit, and register. No change after this.
5. The single run. Sonnet rechecks 20 random trades by hand.

A defect against this document found after the run may be fixed, but the re-run counts as a new trial.

## (g) What each outcome permits

- Pass: eligibility for the January slot and a pre-registered forward ledger, judged alone at the register bar; possibly one separate confirmation on the untouched window under its own registration. Never Live.
- Fail: the library is retired as tested. Nothing is tuned and re-run. The harness is kept.
