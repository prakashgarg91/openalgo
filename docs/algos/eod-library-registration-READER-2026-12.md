# End-of-day library test: owner's reader copy for the freeze review (Monday 14 December 2026)

**NOT REGISTERED, NOT FROZEN, NOTHING RUN.** The single run is planned for the January 2027 slot, and the owner decides.

Written 18 November 2026. The binding text is [eod-library-registration-DRAFT-2026-11-17.md](eod-library-registration-DRAFT-2026-11-17.md) with the code in `services/algos/eod_library.py`. If this copy and those files differ, the files win.

## 1. What is being tested

A fixed library of five simple Nifty weekly option structures is tested on end-of-day prices from April 2021 to October 2026. Each month, the algo for each volatility cell is chosen only from trades that finished in the 12 months before. The question is whether that choosing, with one lot and realistic costs, earns money. Earlier screens have already looked at this window, so the test protects the choosing, not the library. A pass is a reason to test forward in Sandbox mode, not proof of an edge. Nothing here permits trading with real money.

## 2. The five algos

One lot each. Enter at the day's close, exit at the next session's close. No stops or targets, because end-of-day prices cannot show them. The nearest weekly expiry is 1 to 6 calendar days away. ATM is the Nifty close rounded to the nearest 50. A trade is dropped and counted if any leg did not trade on both days. "No trade" is always allowed.

| Algo | Structure | Legs |
| --- | --- | --- |
| A1 | Call credit spread | Sell ATM call, buy the call 200 points above |
| A2 | Put credit spread | Sell ATM put, buy the put 200 points below |
| A3 | Iron condor | Sell call 200 above and buy call 400 above; sell put 200 below and buy put 400 below |
| A4 | Call debit spread | Buy ATM call, sell the call 200 points above |
| A5 | Put debit spread | Buy ATM put, sell the put 200 points below |

## 3. The one tradeable cell: low volatility

Days are grouped 1 to 5 by a fixed volatility model. Groups 1 and 2 are low, group 3 is mid, groups 4 and 5 are high. Only low can trade. Mid and high are counted but forced to no trade. The monthly choice needs at least 40 trades in a cell. Usable trades per algo over the window: low 853, mid 160, high 79. The 40-trade line was met in 100 percent of months for low, 27 percent for mid and 15 percent for high. (These counts come from the brief for this copy, not from a file I could check.)

## 4. Regime constants

Copied from `services/algos/eod_library.py`. They match the values in the brief exactly; there is no conflict.

| Constant | Value |
| --- | --- |
| Coefficient on previous log VIX close | 0.945791 |
| Coefficient on previous session range | 9.33738 |
| Intercept | -7.35624 |
| Cuts | -4.67981, -4.51945, -4.32102, -3.99889 |

The run refits the model and refuses if any value differs by more than 0.0001.

## 5. Event days

Trades whose entry or exit day is on this list get no trade. The sourcing standard: RBI dates are each confirmed on an rbi.org.in press release page. Budget dates each have two agreeing sources. Lok Sabha counting has two sources that are both pre-count schedule statements from 3 June 2024.

| Category | Count | Dates |
| --- | --- | --- |
| Union Budget | 6 | 2022-02-01, 2023-02-01, 2024-02-01, 2024-07-23, 2025-02-01, 2026-02-01 |
| RBI policy | 35 | 2021-04-07, 2021-06-04, 2021-08-06, 2021-10-08, 2021-12-08, 2022-02-10, 2022-04-08, 2022-05-04 (off-cycle), 2022-06-08, 2022-08-05, 2022-09-30, 2022-12-07, 2023-02-08, 2023-04-06, 2023-06-08, 2023-08-10, 2023-10-06, 2023-12-08, 2024-02-08, 2024-04-05, 2024-06-07, 2024-08-08, 2024-10-09, 2024-12-06, 2025-02-07, 2025-04-09, 2025-06-06, 2025-08-06, 2025-10-01, 2025-12-05, 2026-02-06, 2026-04-08, 2026-06-05, 2026-08-05, 2026-10-07 |
| Lok Sabha counting | 1 | 2024-06-04 |

Weak spots named in the file: the 2022-02-01 pair is PRS plus a weekday-only report. The 2024-02-01 pair is an exam-prep site plus a pre-event preview. The primary PIB and indiabudget.gov.in pages returned HTTP 403. The file's top-level "complete" flag is still false.

## 6. How the choice is made

- At each month end, for each cell, look only at trades that exited in the trailing 12 months.
- An algo needs at least 40 trades and a positive mean net per trade. The highest mean wins; ties go to the alphabetically first algo.
- If no algo qualifies, the cell is no trade. The pick applies to the next month.
- Trades are dated by exit day.
- Warm-up: April 2021 to March 2022 (sets the benchmark; not judged).
- Evaluation: April 2022 to October 2026.

## 7. The benchmark: best single algo

In the warm-up, find the low-cell algo with the highest average net per trade. Hold that one algo on every low-cell trade from April 2022, with no monthly choice. If no algo has a positive warm-up average, the benchmark is zero and nothing is held. The hindsight best algo over the evaluation is shown for information only and is not judged.

## 8. Pass checklist

Walk-forward view, realistic costs, unless stated:

- [ ] Net t-statistic at least 2.0
- [ ] Both halves of the evaluation period net positive
- [ ] Worst single day better than a loss of Rs 10,000
- [ ] Largest drawdown under Rs 20,000
- [ ] Net beats the best single algo benchmark
- [ ] Zero days with a loss of Rs 27,000 or more (the daily cap)
- [ ] Still net positive at doubled costs (a separate run that re-selects its own picks)

Anything else is a fail.

## 9. What a pass and a fail each permit

- **Pass:** eligibility for the January 2027 slot and a pre-registered forward test in Sandbox mode. Possibly one separate confirmation on the untouched window, under its own registration. Never Live.
- **Fail:** the library is retired as tested. Nothing is tuned and re-run. The harness is kept.

A defect found after the run may be fixed, but the re-run counts as a new trial.

## 10. Honest limits

- The window was seen by earlier screens, and the library was written by people who knew what worked in it.
- A t of 2.0 is far below the register bar of about 3.8 (0.025 divided by the running trial count).
- Six trials are added. The draft says about 334 to 340; see the conflicts note below.
- End-of-day data cannot test intraday entry times (such as the 10:15 rule in the S3n test), stops or targets.

## 11. Still open before the freeze

- Recount after the event list is marked complete.
- Record the data repository commit that the run uses.
- The run guard refuses until the registration says STATUS: FROZEN, a frozen commit is named, and no guarded file has changed since. It also refuses while the event file's top-level "complete" is false, and when the regime refit misses the constants.
- Expiry-row rule: 7 of 299 listed expiries have no rows on their own date. A label is kept only if its last rows fall 1 or 2 days before expiry, otherwise it is dropped. Eligible sessions: 1,104 to 1,098 (from the brief).

## 12. The owner decides on 14 December

1. Accept the event list, with its named weak spots.
2. Accept the trial count, once it is reconciled.
3. Accept low-volatility-only trading, with mid and high forced to no trade.
4. Freeze the document and code in one commit and register.
5. Approve the single run for the January 2027 slot.

---

**Conflicts found while writing (for the drafting agent):**

- Trial count: settled on 18 Nov 2026. The exploratory looks of 6 and 17 November are now written in `TRIAL_REGISTER.md` (rows 322 to 334, approximate), so six more gives about 340.
- Step (f)1 of the draft requires 40 trades per cell in 90 percent of months. Mid (27 percent) and high (15 percent) fail that, so the gate needs to apply to tradeable cells only.
- The draft cites `services/algos/events.py` as the event list. The code reads `eod_library_events.json` and applies `events.blocking()`.
- The draft cites `services/algos/costs.py`. The code's `trade_net` uses `eod_screen.leg_cost`.
- The draft says expiry exits are clamped to the spread width. `eod_library.py` floors each leg at zero; `clamp_spread_value` is not called in the valuation path.
