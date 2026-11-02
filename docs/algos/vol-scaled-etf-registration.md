# Volatility-scaled equity and gold: registered 2 November 2026, before any code or run

Why: the Opus 5.5 review ranked this first among new ideas: it builds on the one thing the research found predictable (volatility) and trades once a month. The owner lifted the one-new-idea-a-month rule on 2 November 2026 to register and screen it now. This page fixes the rule, costs, data, gates and trial number before any code exists. It is a rejection screen on history already seen many times: a pass would only make it eligible for a forward shadow ledger, which needs its own registration. It places no order and is no expected profit.

## Question

Does holding less Nifty ETF when forecast volatility is high and more when it is low, with the rest in gold and cash, earn more than a passive hold of the same average exposure, after retail costs, on 15 years of daily ETF closes?

## Rule (every number fixed, nothing searched)

- Start with Rs 1,00,000 in cash. Instruments: NIFTYBEES, GOLDBEES and idle cash that earns nothing. Whole shares. The framework's accounting applies: a decision uses closes through one session and trades at the close of the next session; sells first; buys scaled down if cash is short; raw closes, no splits or distributions modelled (so the result is a shadow).
- Decide only at a month-end: the last stored session of a calendar month, judged from the next session, as the other ETF ledgers do. First decision: the first month-end after 300 stored sessions (the same warm-up the other ETF screens use), then every month-end to 30 October 2026. The first signal also buys the starting allocation.
- Forecast volatility on decision day t: sigma = the average of (a) India VIX close on t divided by 100 and (b) the 20-session realised volatility of NIFTYBEES through t (standard deviation of the 20 daily log returns times the square root of 252).
- Target equity weight = the smaller of 0.80 and 0.12 divided by sigma (so Rs 80,000 is the most ever held in equity, the same cap as ETF idea 1). Target gold weight = (1 minus the equity weight) divided by 2. The rest is cash.
- Rebalance only if the current marked equity weight differs from the target by more than 0.05 (five percentage points); then trade both to the target. Otherwise no trade that month. The very first decision always trades.
- No filter, no leverage, no discretionary change, no second signal.

## Benchmarks

- **Exposure-matched passive hold:** NIFTYBEES and GOLDBEES held from the same first trade, never rebalanced, at this ledger's mean marked weights over the whole replay (the framework's existing `hold_matched`), same costs.
- Reported beside it: the static 50/50 hold and a 100 percent NIFTYBEES hold. They take no part in the gates.

## Costs

The repository's frozen itemised ETF schedule (`COSTS_V1`) and its doubled variant, re-sizing the whole-share trades in each, as every ETF ledger does.

## Data and what is untouched

NIFTYBEES and GOLDBEES daily closes from Yahoo (`scripts/algo_backtest/fetch_etf.py`, about 15 years to 30 October 2026) and India VIX daily closes from the private data repository (`context/daily/_INDIAVIX.csv`, from 2008). All of it has been looked at before (the ETF history is development data in earlier screens). No unseen data exists for this idea: only forward days can confirm it.

## Trial

Trial 320 (running count 320). One configuration: target volatility 0.12, equity cap 0.80, forecast the average of VIX and 20-day realised volatility, rebalance band 0.05, monthly. No other value was tried. Any change to any of these, to the costs, or to the gates after seeing a result is a new trial.

## Gates (all six must hold, on the whole replay; the screen can only reject or make eligible)

1. Ending value above Rs 1,00,000 under both the base and the doubled costs.
2. Worst drawdown no more than Rs 20,000 and worst single day no worse than minus Rs 20,000, base costs.
3. Net result above the exposure-matched passive hold's net under both cost variants.
4. The excess over the matched hold is positive in each half of the replay (split at the median session).
5. A one-sided lower bound above zero for the mean monthly excess over the matched hold (rupee change in the ledger's value less the matched hold's, per calendar month), by a moving-block bootstrap (block of 3 months, 200,000 draws, seed 20261102) at the level 0.025 divided by 320.
6. The total excess is still positive after the single best month is removed.

## Reported whatever the result

All six gates with the numbers behind them, the benchmarks above, the number of trades and the costs paid, the deepest fall and worst day, how many calendar years the ledger beat the matched hold and how many it lost, and what failed.

## Limits

Raw closes (no dividends or splits), closes are not executable fills, 15 years is one history with a few large events, and a rule found plausible in advance can still fail. Volatility-managed portfolios are published to rarely beat a hold of the same exposure after costs, which is the most likely outcome here.
