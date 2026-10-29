# Running the ETF rules side by side in sandbox mode

Why: the only family that earned after costs on years it was not chosen on is rotating between a Nifty ETF, a gold ETF and cash ([universe-results.md](universe-results.md)). Most of that is owning equities and gold, not timing. The way to see whether timing adds anything is to run the timed rules next to a plain half and half hold, in sandbox mode, and compare. Nothing here is a promise.

## The three ledgers

All three use `strategies/examples/etf_momentum_rotation.py`, added three times on the Python page, each with its own strategy entry and state file. Orders follow the platform mode, so keep the Analyze badge on.

| Ledger | ETF_MODE | ETF_LOOKBACK | Acts |
| --- | --- | --- | --- |
| Dual momentum | best | 126 | first trading day of the month, 15:15 |
| Trend filter | trend | 100 | every trading day, 15:15 |
| Plain hold | hold | 126 | first trading day of the month, 15:15 |

Settings for each: `ETF_STATE_FILE=strategies/state/etf_<mode>.json`, `DRY_RUN=true` for the first month (it prints the orders it would place), then `false`. The three share one sandbox account, so give each `ETF_CAPITAL=33000` unless you raise the sandbox starting capital.

## What the run can show, and what it cannot

A monthly rule makes about 12 decisions a year. A year of sandbox cannot show an edge. It can show that the machinery is right. It passes after at least 4 monthly rebalances only if:

- every decision equals an offline replay of the same rule on the same days;
- no rebalance is missed or doubled, including around holidays;
- the state file agrees with the sandbox holdings after every trade;
- the price at 15:15 stays within 0.3 percent of the last finished close (each run prints this gap);
- costs stay inside the itemised estimate.

Any mismatch is a fail: fix it and restart the count. After that, whether to use real money is a judgement on the backtest, not on forward proof, and should start small.

## Open points

- The deepest fall of dual momentum on the never-seen years was Rs 25,800, larger than the Rs 20,000 daily limit, so the daily limit never binds here and a total-loss stop is still to be defined. The trend filter's deepest fall was Rs 8,687.
- Its worst single day (Rs 10,517) should be checked against the price data before trusting the other figures.
- The script trades at the 15:15 price; the backtest trades at the close a day after the signal.
- A refused order after an accepted one used to leave the saved holdings out of date. Holdings are now saved after every accepted order and the period is only marked finished at the end.
