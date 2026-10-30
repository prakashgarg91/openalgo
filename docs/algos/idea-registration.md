# Six registered ideas, written down before any is tested (29 October 2026)

Why this page exists: after Zen-type spreads showed no edge, the owner asked for new ideas. They were drafted by GPT-6.1 Sol in the OpenAlgo agent (discussion only, no tool called) from our evidence and data, then written down here, with fixed pass and fail numbers, before any of them is run. Sol's own view was that none of the option ideas is likely to beat simply holding equity plus gold after realistic costs. See [universe-results.md](universe-results.md), [forward-test-registration.md](forward-test-registration.md) and [etf-sandbox-run.md](etf-sandbox-run.md).

Nothing here is an expected profit. Everything runs in sandbox mode or on stored data. Every amount below is a test rule, not a quote or a verified margin.

## Common rules

- Each idea starts with Rs 1,00,000 on its own, no leverage, no averaging down, no combining ideas.
- Whole ETF shares and whole option lots. Use the lot size that applied on each historical date (75 until 29 December 2025, 65 after).
- Charge all historical costs, including 0.1 percent STT on option sells. Every result must also be reported with twice the baseline costs and slippage.
- A signal formed at a close executes at the next session's close, unless an intraday rule says otherwise. A closing mark is not proof of an executable fill.
- Cash earns zero unless an accessible instrument and its return history are named.
- Data already examined is development data, not a holdout. The ETF history (2011 to 2026) and the daily option prices (2022 to 2026) have been examined, so the ETF ideas can only be confirmed forward, in sandbox mode.
- Six ideas are being registered at once, so each statistical test uses a one-sided 99 percent lower bound instead of 97.5. Any change to an idea after a result is a new variant and counts as another trial.
- Trials already spent in this project, to be reported with any result: 150+ option-spread variants, 36 Zen side-rule cells, 48 daily-grid cells, 23 ETF rules, and the three side rules in the forward shadow test.

## The ideas

### 1. Monthly dual momentum, equity ETF or gold ETF or cash
Each month-end compare the 252-session return of NIFTYBEES and GOLDBEES. Hold the one with the higher return if it is positive, else cash. At the next session's close put at most Rs 80,000 in it. The cap does not grow after profits. This is a 252-day variant, not the 126-day rule found earlier, so it is a new trial.
Fails in: a sudden fall before the month-end switch. Illusion: choosing the window or asset universe after seeing results. Risk: a 25 percent overnight fall on Rs 80,000 loses Rs 20,000, so this size can breach the daily limit by construction.
Test: forward sandbox run beside two benchmarks, Rs 50,000 and Rs 50,000 held, and Rs 40,000 and Rs 40,000 held with Rs 20,000 cash. Pass needs all of: CAGR no more than 1 point below the fully invested hold; maximum drawdown at least 25 percent smaller; higher ending wealth than the exposure-matched hold; the same at double costs; no day lost over Rs 20,000.

### 2. Independent equity and gold trend sleeves
Rs 40,000 for each ETF. Hold a sleeve while its ETF closes above its own 100-session average and exit when it closes at or below. Judged daily, executed at the next close. No transfer between sleeves.
Fails in: flat markets (repeated crossings). Illusion: lower average exposure mistaken for timing, so it is compared with a hold of the same average invested capital as well as the full hold. Risk: both sleeves falling 25 percent loses Rs 20,000.
Test and pass: as idea 1, with the exposure-matched benchmark built from this idea's own average invested capital.

### 3. Equity and gold band rebalancing, no forecast
Start with Rs 40,000 NIFTYBEES, Rs 40,000 GOLDBEES and Rs 20,000 cash. At each month-end, rebalance the invested part to equal weights only if equity's weight is below 40 percent or above 60 percent. Invested capital is capped at Rs 80,000; profits above it stay in cash, losses are not topped up.
Fails in: both assets falling. Illusion: calling ordinary equity and gold returns rebalancing alpha, so credit is only the gain over the same start held without rebalancing.
Test and pass: forward sandbox run against the identical un-rebalanced allocation: higher ending wealth after costs and at double costs, and no day over Rs 20,000.

### 4. Debit spread after an ETF breakout
Bullish signal: NIFTYBEES closes above every close of the previous 63 sessions. Bearish: below every close. At the next close, with no position open, use the nearest Nifty expiry with 14 to 35 days left. Buy the call nearest the money and sell the call two listed strikes higher (puts for a bearish signal). One lot, opening debit plus a cost reserve at most Rs 5,000, otherwise skip. Close both legs after five sessions or on an opposite signal.
Fails in: flat markets (false breakouts and decay). Illusion: stale closing prices make the spread look cheaper to buy and dearer to sell than it was; validate against the option bars.
Test: daily real option prices only screen it. A verdict needs 18 untouched months and at least 50 completed trades, whichever takes longer, so it is forward only. Pass: net positive after costs and at double costs, per-trade mean above zero at the 99 percent lower bound, maximum drawdown no more than Rs 20,000, maximum loss per trade no more than the Rs 5,000 budget.

### 5. Long straddle after unusually quiet trading
Signal: the 10-session standard deviation of NIFTYBEES daily returns first falls below the 10th percentile of its previous 252 values. At the next close buy the at-the-money call and put, nearest expiry with 14 to 28 days left, one lot, premium plus cost reserve at most Rs 6,000, otherwise skip. Exit after 3 sessions. No re-entry until the measure has risen back over its threshold and crossed down again.
Fails in: flat and slow-trending markets. Illusion: quiet realised volatility does not mean cheap implied volatility. If the Rs 6,000 cap makes it rarely tradable, that is a failed implementation, not a reason to loosen the cap.
Test: 24 untouched months and at least 40 qualifying trades, whichever is longer. Pass: as idea 4 with the Rs 6,000 budget.

### 6. Intraday failed opening-range breakout, long option
Opening range of Nifty is 09:15 to 09:45. Between 09:45 and 13:00 wait for a completed five-minute index bar to close outside the range, then a later completed bar closing back inside. Buy the at-the-money option in the reversal direction (put after a failed upside break, call after a failed downside break) at the next five-minute option bar's open, expiry at least two days away. One lot, premium plus cost reserve at most Rs 4,000, one entry a day. Exit at the next bar's open once the index closes at the range midpoint or beyond the failed extreme, otherwise at 15:15.
Fails in: strong trends (the return inside is a trap). Illusion: timestamp leakage (buying at an option price from before the signal was known) and omitting spread.
Test: needs paired index and option bars, which the nightly capture now builds (it stores Nifty index minutes and option minutes; the entry uses the option minute after the signal). 12 months of prospective data and at least 100 trades, whichever is longer. Pass: as idea 4 with the Rs 4,000 budget.

## What each result can say

A pass means only that the machinery and the pre-written numbers held in the period tested. A fail ends that version. An idea that is not tradable inside its rupee cap is reported as not tradable. The earliest verdicts are about a year away for the ETF ideas and 12 to 24 months for ideas 4 to 6. Until then every run is sandbox mode only, and a first real use would start with a small amount.

## Limits

- Fills are modelled. Closing prices are not bids and asks.
- A daily stop cannot guarantee a loss ceiling for overnight positions. Gaps can pass it.
- Nothing here shows an edge. It only fixes what we will measure.

## Amendments (version 2026-10-29-v1, written before the first ledger day, after review by GPT-6.1 Sol)

1. Accounting contract for ideas 1 to 3 and their benchmarks, in `services/algos/etf_ledger.py`: every ledger starts as Rs 1,00,000 cash on its own; cash earns nothing and never goes negative; a signal uses closes through the previous session and trades at the next session's close; whole shares; sells first, then buys scaled to what the cash can pay including charges; leftover cash stays idle; costs are the itemised schedule in `services/algos/universe.py` (frozen as of this date) and the doubled-cost variant re-runs the sizing with every charge doubled.
2. First signal date is 30 October 2026, so the first trade is the following session's close. Every ledger and benchmark starts from cash on that close. Month-end means the last stored session of a calendar month, judged from the next stored session.
3. Benchmarks are held, not rebalanced: Rs 50,000 and Rs 50,000; Rs 40,000 and Rs 40,000 with Rs 20,000 cash; and, for each idea, an exposure-matched hold whose NIFTYBEES and GOLDBEES weights are the mean post-trade weights of that idea on a replay of 18 January 2013 to 29 October 2026 (written once to `db/etf_ledger/matched_weights.json`, never recomputed from forward results). After amendment 7 below they are: idea 1 about 32 percent Nifty ETF and 20 percent gold ETF, idea 2 about 24 and 20, idea 3 about 30 and 29.
4. Certification: forward results are labelled SHADOW and provisional because splits and distributions are not modelled and prices are raw closes. A missing close on a stored session blocks the run; it is never filled forward. A correction regenerates the affected sessions and the original output is kept.
5. The nightly capture now also saves NIFTYBEES and GOLDBEES daily closes (about 14 months), and the Windows task runs `scripts/algo_backtest/run_etf_ledgers.py` after the capture. It places no order.
6. Not built: orders, broker connection, a dashboard, an optimiser, new signals, or any change to a rule after seeing results.
7. Found and fixed on 30 October 2026, before any ledger session existed, so the version is unchanged: the first version of the ledger re-bought a held position to its rupee target on every signal day (daily for idea 2), which paid charges again and again (Rs 1,07,000 of charges over 13.8 years in a screening run) and is not what ideas 1 and 2 say. The rule is now: a position that is already held and whose signal is unchanged is not traded. The rupee cap is a cap: at a month end a held position that has grown more than 5 percent past its cap (Rs 80,000 for idea 1 and for the invested part of idea 3, Rs 40,000 for each idea 2 sleeve) is trimmed back to the cap, which keeps exposure from compounding past what was registered. The 5 percent tolerance avoids paying charges on a few shares. The exposure-matched weights in amendment 3 were recomputed under this rule before the first ledger day. A later change of this kind starts a new version.
