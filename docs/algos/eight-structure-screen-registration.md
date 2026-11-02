# Eight-structure rejection screen on NSE end-of-day data: registered 2 November 2026, to be run once on or after 1 December 2026

Nothing here has been run. This page fixes the structures, the data, the costs, the gates and the trial count before any number is looked at. A screen on stored history can only reject; it never promotes. At most two survivors go on to a forward shadow ledger of their own (registered separately), and zero is the likely result.

## Why and when

The two intraday years have been examined many times, so they cannot confirm anything new. The NSE end-of-day history ([nse-eod-registration.md](nse-eod-registration.md)) reaches back to 2015. The owner asked on 2 November 2026 to register the screen in November and run it once in December. The November idea slot was already used by C1, so the run is the December idea slot: the trials are added to the register when the run happens, as numbers 312 to 319 (running count 319). The screen is not run before 1 December 2026, and not repeated.

## Data and periods (fixed now)

- **Prices:** `openalgo-data/nse_fo_eod/` (Nifty index options, end of day, close and settlement price). Entry fills are at the day's close of each leg. A leg with no trade (contracts 0) or a zero close on the entry day makes that week "not counted", recorded with its reason and never filled in.
- **At the money:** the strike where the call close and the put close are closest on that expiry (both traded), spot taken as strike plus call minus put, rounded to the nearest 50. The file's own underlying price exists only from July 2024, so it is not used.
- **Expiry value (corrected 2 November 2026, before any run):** on an expiry date the file's `settle` column holds the index's final settlement price, the same number on every strike (zero before February 2020), not the option's own value. An option's value at expiry is therefore its intrinsic value against that price (a call: the settlement less the strike, never below zero; a put the other way round). A week whose expiry-date rows disagree on that price, or carry none, is not counted. This replaces the earlier wording that read the column as each option's settlement price; the first version of the engine did that, which an audit caught from the data on 2 November, and it was fixed with a test on the real layout. It is a correction, not a new trial, and no result had been looked at.
- **Lot size:** by expiry, from `services/algos/nse_lots.py`, which cites the exchange's own circulars (NSE/FAOP/47854, 61415, 64625 and 70616, all opened and read on 2 November 2026). Expiries before 1 April 2021 have no documented lot, so the screen excludes them: the August 2015 revision (press reports 25 to 75) is not backed by a circular that has been opened. If that circular is found and added to the table, with a test, before the run, the period before April 2021 may be added and reported separately. No lot is guessed.
- **Primary period (never used for any option test):** expiries from 1 April 2021 to the last expiry before 3 October 2024 (the first expiry in the two intraday years). Survival is decided here and only here.
- **Overlap period (already seen in every earlier study):** expiries from 3 October 2024 to 27 October 2026. Reported for completeness; it takes no part in any decision.
- **Filters:** the earlier ones, evaluated on the entry day's close: no entry if India VIX closed at 20 or higher (`context/daily/_INDIAVIX.csv`), and for call-side structures no entry if the Nifty fell 1 percent or more from the previous close on the entry day, for put-side structures none if it rose 1 percent or more. Condors, the calendar and the straddle use the VIX filter only.

## The eight structures (each one lot, held to expiry, no stop, no target, no adjustment)

Weekly structures enter at the close two sessions before the weekly expiry (the session count is read from the stored sessions); monthly structures at the close five sessions before the month's last expiry (the last expiry of the calendar month in the data).

1. **WC, weekly call spread:** sell the at-the-money call, buy the call 100 points above. This is S3n entered at the close instead of 10:15.
2. **WP, weekly put spread:** sell the at-the-money put, buy the put 100 points below.
3. **MC, monthly call spread:** as 1 on the monthly expiry.
4. **MP, monthly put spread:** as 2 on the monthly expiry.
5. **WK, weekly condor:** sell the call 150 above and the put 150 below the money, buy the call 400 above and the put 400 below (the geometry of the earlier S2).
6. **MK, monthly condor:** the same geometry on the monthly expiry.
7. **CAL, calendar:** sell the at-the-money call of the weekly expiry, buy the same strike call of the next monthly expiry. The weekly leg expires at its intrinsic value; the monthly leg is closed at that day's close. A week whose two legs have different lot sizes is not counted.
8. **STR, long straddle (control):** buy the at-the-money call and put of the weekly expiry. It is the buyer of the variance premium that the earlier tests found real but not reliably extractable. It is expected to lose. If the control passes every gate, the data or the cost code is suspect and the other seven results are not read until that is explained.

## Costs

`services/algos/costs.py` (Rs 20 an order, STT, exchange charges, GST, stamp duty, 0.15 points slippage a leg a side) and its doubled variant, with the lot from the table above. Two known biases are stated now: the STT rate in that file is 0.10 percent before April 2026 and so overstates the real rate before October 2024 (conservative), and the STT charged when an in-the-money option is exercised at expiry is approximated by the same rate on the intrinsic value (the exchange rate was 0.125 percent). Condors and the calendar are costed leg by leg with the same schedule. The doubled variant covers both.

## Survival gates (all in the primary period; every one must hold)

1. At least 100 completed trades for a weekly structure (WC, WP, WK, CAL, STR), at least 30 for a monthly one (MC, MP, MK).
2. Net profit above zero under the realistic costs and above zero at twice them.
3. Worst drawdown marked to market at each day's close, and worst single day, each no more than Rs 20,000 for one lot.
4. Net profit still above zero after the single best trade is removed.
5. Net profit above zero in each half of the primary period (split at the median trade date).
6. A lower bound above zero for the mean net result per trade, by a moving-block bootstrap over trades (block 3, seed 20261201), taken at the level 0.025 divided by 319, the running trial count after this screen (rule 3 of [TRIAL_REGISTER.md](TRIAL_REGISTER.md)), with 200,000 draws so that level is resolvable. Amended on 2 November 2026, before any run: the first version of this gate used the 97.5 percent bound (level 0.025) with 10,000 draws; the stricter bar is the register's own rule.

If more than two pass, the two with the smallest worst drawdown go forward (ties by larger net). A survivor still needs its own registration, costs and gates before it is run forward, and the one-new-idea-a-month rule applies to those registrations.

## Reported whatever the result

All eight structures with trades counted, weeks not counted and why, realistic and doubled net, drawdown, worst day, the split by halves and by the sign of the Nifty's return over the 20 sessions before entry, the result in the overlap period, how many of the eight lost money in the primary period (the "untouched" period for this purpose), what failed and which gate it failed, and the running trial count (319 after the run). No parameter, width, entry day or filter is changed after the results are seen; any change is a new trial and needs new data.

## Limits

End-of-day close fills are kinder than real fills (no bid, no ask, no time of day), so a pass is an upper bound; the file has no price for a leg on a day it did not trade; the primary period is about three and a half years, so even a survivor has wide uncertainty, and it is mostly a rising Nifty with one fall in 2022. A structure that passes here is a candidate for a forward shadow ledger, not a strategy.

## Build status (2 November 2026)

The engine is built and tested on made-up prices (`services/algos/eod_screen.py`, `test/test_eod_screen.py`); the script `scripts/algo_backtest/eight_structure_screen.py <data_repo>` refuses before 1 December 2026 and refuses a second run, and writes its report to `research/eight_structure_screen/report.json` in the data repository. `--check` (coverage counts only, no prices) found 185 weekly and 42 monthly expiries with a documented lot in the primary period and 114 and 25 in the overlap period. No result has been looked at.

## Audit notes (2 November 2026, before any run)

- The screen can only be run once per repository, not per copy of the data: running it writes `docs/algos/eight-structure-screen-run.txt`, which must be committed, and the script refuses while that file exists.
- Exchange charges: `costs.py` uses a flat 0.0345 percent; the actual rate was about 0.05 percent over 2021 to September 2024. STT is overstated by more (0.10 against 0.0625 percent), so costs stay conservative overall, but the screen's report must say so.
- The bootstrap gate now uses the register's rule 3 (0.025 divided by 319); see gate 6 above. A forward ledger of a survivor uses the same engine and so the same bar. The earlier S3n and C1 registrations keep the levels they were registered with.

