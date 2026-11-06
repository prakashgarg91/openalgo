# Zen reconciliation against our own option candles (6 November 2026)

Question: are Zen's 216 real trades (downloaded from Stratzy, kept in the trading-rex-ai folder, never copied into a public repository) consistent with real market prices as our own 5-minute option candles record them?

Method: `scripts/algo_backtest/zen_reconcile.py` (parser `services/algos/zen_trades.py`). For each trade it takes Zen's entry and exit times and the two strikes, finds the 5-minute candles at those moments in `openalgo-data/bars5m`, and compares Zen's entry credit, exit debit and result with ours. Output: `openalgo-data/research/zen_reconcile/` (private). Read only, no order.

## Result

- 208 of 216 trades could be compared; 8 had no exit candle. 109 put spreads, 99 call spreads.
- Entry credit: median difference minus 0.22 points, 93 percent within 8 points. Exit debit: median difference plus 0.32 points, 86 percent within 8 points.
- Per-trade result, ours against Zen's: correlation 0.988. Total points: Zen 2,239, ours 2,152 (within 4 percent).
- So the vendor ledger is consistent with real prices at the stated times, and our candles can replay Zen's trades.

## Rough result after our cost model (assumed leg prices, so approximate)

| | Trades | Net after costs | Win rate |
| --- | --- | --- | --- |
| All, at Zen's own lots (2 to 6) | 208 | about Rs 6.0 lakh (costs about Rs 70,000, Rs 338 a trade) | |
| Call spreads (bear call) | 99 | about Rs 5.53 lakh | 59 percent |
| Put spreads (bull put) | 109 | about Rs 0.48 lakh | 52 percent |
| July to December 2025 | 84 | about Rs 2.54 lakh | 55 percent |
| 2026 | 124 | about Rs 3.47 lakh | 56 percent |
| All, one lot (Rs 1 lakh account) | 208 | about Rs 1.32 lakh | |

One lot: deepest fall about Rs 27,000 (above the Rs 20,000 daily limit), worst single trade about Rs 14,000.

## What this does not show

- It is one 14-month stretch, replayed on trades Zen had already made. It says nothing about whether Zen's side and timing choices will keep working. The call spreads earned most of it; the other project's notes disagree on whether the market rose or fell in this window, so the call spread edge may depend on the regime. Check against the Nifty path before leaning on it.
- Zen's rules for choosing the side and the time are not published and are not recovered by this test.
- The costs here use assumed leg prices; the exit class (stop, target, time) is not in the file.
- Reconciliation earlier than 2025-07 and after the last stored expiry is not possible with the stored candles.
- This corrects the earlier note in `stratzy-comparison.md`: Zen's real trades do replay on real prices, and they earned in this window.
