# Intraday test of Zen's rules (needs Upstox Plus)

The daily tests cannot see a 10:15 entry, a stop inside the day or a profit target, which is where Zen's result is decided (see `stratzy-comparison.md`). This runs those on real 5-minute option prices.

Nothing here places an order. The fetcher only reads, and the replay only reads files on disk.

## What you need

- Upstox **Plus plan**. Expired-contract history is not served on the free plan. Without it the fetcher stops and says so.
- A read-only Upstox token in the environment: `UPSTOX_ANALYTICS_TOKEN` (or `UPSTOX_ACCESS_TOKEN`). It is never printed or written to a file.
- The daily files the earlier tests already use (history and NSE option days), and the published trade table (not stored here).

## Steps

```bash
# 1. See how many requests it will make, without making any
uv run python scripts/algo_backtest/fetch_upstox_expired.py <history_dir> <nse_days_dir> <bars_dir> 2025-07-01 2026-10-26 --dry-run

# 2. Download (resumable: stop and run again, finished files are skipped)
export UPSTOX_ANALYTICS_TOKEN=...
uv run python scripts/algo_backtest/fetch_upstox_expired.py <history_dir> <nse_days_dir> <bars_dir> 2025-07-01 2026-10-26

# 3. Validate, then run the rule grid
uv run python scripts/algo_backtest/stratzy_zen_intraday.py <history_dir> <bars_dir> <table.md>
```

For July 2025 to October 2026 the dry run counts 70 weekly expiries and about 4,300 requests, roughly 45 minutes at the default pause. One file per contract is written as `<expiry>_<CE|PE>_<strike>.csv`.

## What the replay does

- The decision at 10:15 uses only bars that closed by then. Spot comes from put-call parity of the at-the-money strikes, so no index feed is needed. The entry fill is the open of the 10:15 bar.
- It sells at the money and buys 400 points away, on the nearest weekly expiry.
- Each bar is checked in this order: exit time (15:00 or later on a later session), stop, target, expiry.
- The stop is 43.8 points over the credit. It uses the pessimistic spread high, fills at the trigger plus 2 points of slippage, or at the bar open when the price gaps through.
- The target is a spread value of 10 points or less at a bar close.
- A stop before 14:30 reopens on the other side at the next bar, up to three times a day.
- A position held overnight blocks the next entry. India VIX of 20 or more, or a 1% gap down, keeps it out.

## How to read the result

Part 1 replays the 204 published entries and compares the result with what was published: entry price error, points per trade, stops. It must reproduce the published result (correlation 0.8 or more, total within 25%) before part 2 is shown. If it does not, the stop or target rule is wrong, or the published fills are not what the market printed, and a rule grid built on them proves nothing.

Part 2 is 36 pre-registered cells (6 side rules, 3 exit styles, 2 filters) in thirds of the period. Count the cells that lose in the last third before believing the winner. Stops fill at the trigger in this replay, which is kinder than a live market stop, so a thin edge here is not an edge.

## Limits

- 5-minute bars hide what happened inside a bar. The stop assumes the worst high; the target needs the close.
- A leg with no trade in a bar carries its last close. Far out-of-the-money legs trade rarely.
- Bars have no bid or ask, so slippage is the conservative cost model plus 2 points on stops.
- Lot size is 75 before 30 December 2025 and 65 after; points are the figure to trust across the change.
