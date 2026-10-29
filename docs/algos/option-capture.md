# Nightly capture of weekly Nifty option candles

Why: every test of Zen's rules so far needed Upstox's paid Plus plan to read expired contracts. Contracts that are still live can be read on the free feed, so saving each evening's 1-minute candles builds the same history, and the later days it collects are data nobody has tuned a rule to. That is the holdout the October 2026 test lacked (see [stratzy-comparison.md](stratzy-comparison.md)).

Nothing here places an order. It reads candles and writes them to the Historify database.

## What it saves

- The Nifty index minute candles of the last week and the India VIX daily closes of the last six weeks, which the forward shadow test ([forward-test-registration.md](forward-test-registration.md)) reads.
- The nearest Nifty weekly expiry, calls and puts, 16 strikes either side of the at-the-money strike (about 800 points) taken from the Nifty close of the day, widened to cover the day's whole Nifty range and the previous session's range plus 500 points, so the far leg of a 400-point spread opened earlier is stored even after a big move. Days captured before 29 October 2026 evening used the plain band.
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

On Windows, double-click `scripts/algo_backtest/windows/install_capture_task.cmd` instead. It creates a Task Scheduler task, "OpenAlgo option capture", for Monday to Friday at 16:00 on the computer's clock, running `capture_option_candles.cmd` next to it, which writes to `log\capture.log`. Set the token once first with `setx UPSTOX_ANALYTICS_TOKEN your-token`, then sign out and back in. The computer must be on and you must be signed in at that time; a missed day is not made up. Check it with `schtasks /run /tn "OpenAlgo option capture"` and read `log\capture.log`.

Antivirus note for Windows: Avast sets a `SSLKEYLOGFILE` variable that points at one of its own devices. Python exits silently, with the line `no OPENSSL_Applink`, the first time it opens a secure connection, so `uv run app.py` and the capture both fail. `capture_option_candles.cmd` clears the variable for its own run. For the app, clear it first in the same terminal (`set SSLKEYLOGFILE=`). The same antivirus also made the first scheduled run slow: importing pandas took 59 seconds inside the task against half a second by hand. A later run finished in under two minutes. If yours stays slow, add the OpenAlgo folder to the antivirus exclusions.

It prints how many contracts it saved. Exit codes: 0 all saved (or a weekend); 2 a contract or the index/VIX context failed, or nothing was saved; 3 a weekday with no Nifty candles. Upstox answers a refused token and a market holiday the same way, with no candles, so 3 cannot tell them apart: on an exchange holiday it is expected, on any other day check the token. A contract that fails is skipped and counted.

## Reading it back

Use the Historify page or `database.historify_db.get_ohlcv(symbol, "NFO", "1m", ...)`. Contract names are the OpenAlgo symbols, for example `NIFTY04NOV2525000CE`.

## Limits

- It saves candles, not bid and ask, so fills still cannot be measured from it.
- It captures the nearest expiry only. A contract is captured from the expiry week; earlier days of that week are not back-filled.
- Verified on Windows on 29 October 2026, after the close, with the master contract downloaded and the Upstox analytics token set: 66 contracts for the 03-NOV-26 expiry around Nifty 22937, all 66 stored, 25,063 one-minute candles, 0 failed. One contract read back from Historify gave 385 rows from 09:15 to 15:39 with open interest and unique timestamps (the index itself gave 375). The Windows task was created, run with `schtasks /run` and finished with result 0; a re-run stored the same 66 contracts without duplicates.
- Not verified: a run that fires by itself at 16:00 (only manual triggers so far), a holiday, a week with an expiry change, and the days the computer is asleep or signed out. The capture is paced at 3 requests a second with a 60-second wait and one retry after a rate-limit reply, because the analytics token is shared with another application; that rate-limit path has only been tested on fakes. Why the last 10 minutes after 15:30 hold candles was not investigated.
- The job is a command you schedule. It is not wired into the app's own scheduler, so it adds no thread or connection to the running server.
