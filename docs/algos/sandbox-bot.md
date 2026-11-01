# Sandbox bot and forward test alerts

Two additions beside the forward shadow test ([forward-s3n-registration.md](forward-s3n-registration.md)). Neither places a live order and neither changes any registered rule.

## Evening alerts (Telegram)

`scripts/algo_backtest/alert_forward.py` runs in the nightly job after the capture and the ledger run. It sends a plain-language message when:

- the capture did not finish cleanly (token refused, some candles not saved, or it stopped early), saying what to do;
- a weekday between the last stored session and today has no stored candles (a market holiday also triggers it, and the message says to ignore it then);
- a week is not counted, a week is entered, a week closes (with the realistic net), or the test stops or finishes.

Each event is sent once (`db/forward_s3n/alerted.json`). Alerts reach Telegram only while the OpenAlgo Telegram bot is on and you have notifications enabled; they are always written to `log\capture.log`. If the PC is off at 16:00 nothing runs, so nothing is sent that night: the next night's run names the missed day.

## Sandbox bot

`scripts/algo_backtest/sandbox_bot.py` places the same two legs through the OpenAlgo API so the fills can be compared with the ledger's candle fills. The ledger tests the idea; the bot tests whether the orders would have filled.

- **Sandbox only.** Before every action it asks OpenAlgo for the mode and does nothing unless analyzer (sandbox) mode is on.
- **One lot** (65), product NRML (the spread is held across sessions), strategy name `S3n-sandbox`.
- **Entry** (`entry`, run at about 10:15 on the entry session): the registered filters (India VIX of the previous close below 20, no 1 percent gap down), strikes at the money and 100 points above, then the bought call at the ask. The call is sold at the bid only after the bought call is filled; a hedge that does not fill in 60 seconds is cancelled and nothing is sold. If the call does not fill, the hedge stays and is recorded as an orphan until `exit` closes it.
- **Check** (`check`, run at about 10:20 and 15:00): confirms both legs are held; a sold call without its hedge raises an alert.
- **Exit** (`exit`, run at about 15:25 on the expiry session): buys the call back first, then sells the hedge, with market orders. Before the expiry session it refuses, unless `--force` is given to close by hand.
- **Compare** (`compare`, after the nightly ledger run): appends the bot's credit and exit value against the ledger's to `db/sandbox_bot/compare.csv` (positive shortfall means the bot did worse). A steady shortfall is the measured slippage the cost scenarios currently assume at 0.15 points.
- `--dry-run` on `entry` and `exit` prints the plan and places nothing.

Set `OPENALGO_API_KEY` (and `OPENALGO_HOST` if OpenAlgo is not on `http://127.0.0.1:5000`) on the PC, and keep OpenAlgo logged in to the broker and in analyzer mode. The bot is not scheduled automatically: run the four commands by hand for the first weeks (or add Task Scheduler entries once you trust them).

## Limits

Sandbox fills are produced by the sandbox engine, not by a real order book, so the shortfall it shows is an indication only; real bid/ask snapshots ([bid-ask-snapshots.md](bid-ask-snapshots.md)) remain the measure of slippage. Tested on a fake API only; it has not yet been run against a live OpenAlgo in analyzer mode.
