# Where Zen operates, and how ours differs

Question asked: Zen looks very good in bullish markets on Stratzy, and many of its algos seem to work. Where does it operate, and how does our system differ?

## What Stratzy publishes about Zen

Sources: the Stratzy community pages for Zen (algo-spotlight-3), Gamma-Fluxer (13) and Theta Harvest (14), and the Dhan listing for Stratzy. The Stratzy marketplace page itself returned 403, and the Dhan page is rendered in the browser, so Zen's own figures came only from a search summary.

| Item | Zen as published |
| --- | --- |
| Instrument | Nifty options |
| Structure | Overnight, hedged credit spread; bull put in a bullish read, bear call in a bearish one |
| Timing | Entered near the close, exit at 3:00 PM the next day |
| Conditions | Works best when India VIX is 13 to 20 |
| Capital | Rs 1 lakh and above |
| Signals | Not disclosed |
| Returns shown | Backtests or unlabelled; Dhan shows 24.08% over 3 months on Rs 1 lakh, labelled a backtest |

Nothing found is a live, audited track record. The sibling algo Gamma-Fluxer is described with success under 50% and drawdown above 60%, "Very High" risk. "Very good in bullish" cannot be confirmed from public pages.

## How ours differs

| | Stratzy Zen | Ours |
| --- | --- | --- |
| Structure | Overnight hedged credit spread | The same: bull put or bear call, 150-point width |
| Exit | 3:00 PM next day | Next morning, 09:45 |
| VIX | Best at 13 to 20 | No band; calm and trending regime days only |
| Side | Undisclosed | Follows the regime lean |
| Stop and target | Undisclosed | 30% stop, 90% target of premium |

So the shape is the same. The two real differences are the exit time and the VIX band.

## Test on real option prices (2022-01 to 2026-10, 1,188 days)

Script: `scripts/algo_backtest/stratzy_compare.py`. Full output: `docs/algos/stratzy-comparison-output.txt`. Grid fixed before any result was read: shape (OTM1/4, OTM2/5) x side (follow the lean, bull put only on bullish days) x exit (next open, next close standing in for 3 PM) x VIX band (none, 13 to 20). One lot, itemised costs, expiry eve skipped. Stops and targets cannot be replayed on daily prices and are left out of both.

Totals in rupees for one lot (OTM1/OTM4; OTM2/OTM5 is within a few thousand):

| Variant | All days | Win rate | 2022-23H1 | 2023H2-24 | 2025-26 (untouched) |
| --- | --- | --- | --- | --- | --- |
| Follow lean, exit open, any VIX (ours) | -93,490 | 42% | +5,990 | -37,687 | -61,794 |
| Follow lean, exit open, VIX 13-20 | -48,549 | 42% | +5,491 | -28,152 | -25,888 |
| Follow lean, exit close, any VIX | -134,260 | 57% | +31,924 | -60,166 | -106,019 |
| Bull put only, exit open, any VIX | -19,354 | 47% | +476 | -7,703 | -12,127 |
| Bull put only, exit close, any VIX | +940 | 63% | +15,572 | +1,500 | -16,132 |
| Bull put only, exit close, VIX 13-20 | -9,171 | 57% | +2,029 | +2,825 | -14,025 |

All 16 cells lost money in the untouched last period.

## What this says

1. **Exiting at the close lifts the win rate from about 42% to 57-65%, but not the money.** A strategy shown with a 60%+ win rate can still be flat or negative, because the losses are several times the wins. If Stratzy leads with win rate, this is the likely source of "earning very well".
2. **Bullish-only is better than following the lean.** Bear calls in a rising market are most of our losses. Bull put only on bullish days roughly breaks even with a close exit (+940 over nearly five years), against a clear loss when following the lean.
3. **The 13-20 VIX band narrows the loss but did not make it profitable.** It helped follow-lean (-93k to -49k) and hurt bull-put-only.
4. **Bullish does not mean a bull market in the data.** 2022 to mid 2023 was good for every variant; 2025-26 was bad for every variant. A recipe that "earned very well in bullish" is consistent with having been shown on a bullish stretch.
5. **Nothing here earns on real prices.** This matches the earlier mandate and universe searches.

## What this does not show

- The 3 PM exit is approximated by the next close. An exact 3 PM price needs intraday option data we do not have.
- Stratzy's signals are undisclosed, so only the published parts are tested.
- Daily data cannot replay stops and targets, which may matter more than the exit time.
- One lot, no slippage beyond the itemised costs.

## Decision

No change to the live engine. The two published differences do not pass the untouched period. The close-exit option stays research only in `run_lab(exit_field="close")`. The bull-put-only finding is a lead, not an edge: it breaks even before the last period turns it negative.
