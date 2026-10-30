# Historify data dictionary (what the nightly capture stores)

For anyone, human or tool, reading the stored candles. Read the dated snapshot, not the live file:
`db/snapshots/historify-YYYYMMDD.duckdb` is written by `scripts/algo_backtest/snapshot_historify.py` after each evening's capture and is never written to again. Open it read-only (`duckdb.connect(path, read_only=True)`). The live file `db/historify.duckdb` can be locked by the app or the capture. The newest 30 snapshots are kept.

## Table `market_data`

| Column | Type | Meaning |
| --- | --- | --- |
| symbol | text | OpenAlgo symbol, upper case (see naming below) |
| exchange | text | NFO (option contracts), NSE_INDEX (Nifty index, India VIX), NSE (ETFs) |
| interval | text | `1m` one-minute candles, `D` daily |
| timestamp | integer | Unix seconds in UTC. India time is UTC plus 5:30, so a 09:15 IST candle is 03:45 UTC |
| open, high, low, close | float | Prices in rupees. Index and VIX are points |
| volume | integer | Contracts or units traded in the candle |
| oi | integer | Open interest at the end of the candle, option contracts only (0 where not available) |
| created_at | timestamp | When the row was first written |

The primary key is (symbol, exchange, interval, timestamp), so saving the same day twice replaces rows and never duplicates them.

## What is stored

- Option contracts: `NIFTY<DD><MON><YY><strike><CE|PE>`, for example `NIFTY03NOV2623450CE` (exchange NFO, interval 1m). The nearest weekly expiry, 16 strikes either side of the money by the day's close, plus the far leg of any 400-point spread opened that day. Candles run 09:15 to about 15:39 India time.
- Nifty index minutes: `NIFTY` on `NSE_INDEX`, 1m, the last week each night, 09:15 to 15:29.
- India VIX: `INDIAVIX` on `NSE_INDEX`, interval `D`, about six weeks.
- ETF closes: `NIFTYBEES` and `GOLDBEES` on `NSE`, interval `D`, about 14 months.

## Cautions

- Candles are not bid and ask, so fills cannot be measured from them.
- A candle with no trade may be missing, not zero: do not forward-fill across contracts.
- The first day stored is 29 October 2026 for options. Earlier days are not back-filled.
- ETF closes are raw, so splits and distributions are not adjusted.
- Each day is read from the Upstox free feed after the close. A day the capture missed is not made up.
