# Nightly capture of weekly Nifty option candles

Why: every test of Zen's rules so far needed Upstox's paid Plus plan to read expired contracts. Contracts that are still live can be read on the free feed, so saving each evening's 1-minute candles builds the same history, and the later days it collects are data nobody has tuned a rule to. That is the holdout the October 2026 test lacked (see [stratzy-comparison.md](stratzy-comparison.md)).

Nothing here places an order. It reads candles and writes them to the Historify database.

## What it saves

- The nearest Nifty weekly expiry, calls and puts, 16 strikes either side of the at-the-money strike (about 800 points), taken from the Nifty close of the day.
- One-minute candles for that day, with open interest, stored in Historify as exchange NFO, interval 1m. No schema change, so there is no migration to run.
- Re-running the same day is safe: Historify updates rows instead of duplicating them.

## Set up

1. Log in to your broker once so the master contract is downloaded (the capture looks contracts up in it).
2. Put your read-only Upstox token in the environment as `UPSTOX_ANALYTICS_TOKEN`. It needs no static IP.
3. Check what it would save, without saving:

```bash
uv run python scripts/algo_backtest/capture_option_candles.py --dry-run
```

4. Run it every trading day after the close, for example Monday to Friday at 16:00 India time. With cron on the server:

```
0 16 * * 1-5  cd /path/to/openalgo && uv run python scripts/algo_backtest/capture_option_candles.py
```

It prints how many contracts it saved. On a market holiday it finds no Nifty candles, says so and saves nothing. A contract that fails is skipped and counted; the exit code is 2 if any failed.

## Reading it back

Use the Historify page or `database.historify_db.get_ohlcv(symbol, "NFO", "1m", ...)`. Contract names are the OpenAlgo symbols, for example `NIFTY04NOV2525000CE`.

## Limits

- It saves candles, not bid and ask, so fills still cannot be measured from it.
- It captures the nearest expiry only. A contract is captured from the expiry week; earlier days of that week are not back-filled.
- It was tested on fakes and has not yet been run against a live feed on a machine with the master contract downloaded.
- The job is a command you schedule. It is not wired into the app's own scheduler, so it adds no thread or connection to the running server.
