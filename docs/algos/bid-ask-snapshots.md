# Bid and ask snapshots

Why: every cost result in this project rests on an assumed slippage per fill, because the candle data has no bid and ask. The registered realistic cost scenario ([cost-scenario-registration.md](cost-scenario-registration.md)) assumes 0.15 points per fill, and the sign of the spread results depends on that number. This collects the real quoted spread so the assumption can be replaced by a measurement. Nothing here places an order: it reads quotes and writes a CSV file.

## What it saves

Three times a day (10:15, 14:30 and 15:00 India time, the entry and exit times the tests use), the best bid and best ask, last price, volume and open interest of every call and put of the nearest weekly Nifty expiry within about 800 points of the money (about 66 contracts, one request). Rows go to `<data repository>/bidask/YYYY-MM-DD.csv` with the distance of each strike from the index, the spread in points and as a share of the mid. A contract with no bid or no ask keeps its row with an empty spread, because a missing side is itself a finding.

## Set up on the Windows computer

1. Run `scripts/algo_backtest/windows/download_research_data.cmd` once, so the data repository sits next to the OpenAlgo folder.
2. Set the read-only token once: `setx UPSTOX_ANALYTICS_TOKEN your-token`, then sign out and in.
3. Check one snapshot by hand during market hours: `scripts\algo_backtest\windows\snapshot_bidask.cmd 1015`, then read `log\bidask.log` and `..\openalgo-data\bidask\`.
4. Double-click `scripts/algo_backtest/windows/install_bidask_tasks.cmd`. It creates three tasks, "OpenAlgo bid-ask 1015", "1430" and "1500", for Monday to Friday. The computer must be on and signed in at those times; a missed snapshot is not made up.
5. `download_research_data.cmd` commits and pushes the `bidask` folder with the other data.

Exit codes: 0 saved (or a weekend); 1 the token or master contract is missing; 2 no quotes came back; 3 a weekday with no Nifty price (an exchange holiday, or Upstox did not accept the token: on any day the exchange was open, check the token).

## Reading it

`uv run python scripts/algo_backtest/summarize_bidask.py ../openalgo-data` prints the median quoted spread by moment, call or put, and distance from the money, and how many days there are.

## How it will be used (fixed now, before any data exists)

After about 60 trading days the median quoted spread at the strikes a structure trades (the short leg near the money, the long leg 250 to 400 points out) is read off. Half of it is the slippage a market order pays per fill. If that differs from 0.15 points the cost scenario is re-run once with the measured figure, and that third scenario is registered before it is applied. No other use is made of the snapshots, and no rule is chosen from them.

## Limits

Best bid and ask only (no depth quantity), a quote is not a fill, a thin strike can quote wide and still trade inside it, and about 60 sessions is enough to set a cost but not to judge a strategy. Quotes are for the live weekly expiry only.
