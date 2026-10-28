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

## Their Past Trades page, checked against our data

Six screenshots of the Zen Past Trades tab (Jun to Oct 2026 calendars and the drawdown chart) were transcribed into `stratzy-zen-past-trades-2026.csv` (67 trading days). The monthly sums match the on-screen month totals, so the transcription is right. Script: `scripts/algo_backtest/stratzy_pasted_days.py`.

What the page shows, in rupees:

| Month | Trades | Result | Nifty that month |
| --- | --- | --- | --- |
| Jun 2026 | 14 | +2.14L (+66.84%) | +1.35% |
| Jul 2026 | 14 | +78.26k (+24.46%) | +2.17% |
| Aug 2026 | 15 | +27.09k (+8.47%) | -1.24% |
| Sep 2026 | 12 | +68.82k (+21.51%) | -6.06% |
| Oct 2026 (to 27th) | 12 | -32.40k (-10.12%) | +0.59% |

Findings:

1. **The percentages are on about Rs 3.2 lakh, not Rs 1 lakh.** Every day divides back to roughly Rs 3,20,000. The five months add up to about +3.6L on that base.
2. **It is not a bull-market result.** September 2026 fell 6% and the algo made +21.5%; June rose 1.35% and it made +66.8%. Across the 67 days, the sign of the daily result matched the sign of Nifty's next-day move 50% of the time, with correlation near zero (+0.04 if the date is the entry day, -0.07 if it is the exit day). A bull put spread that profits from rising prices would show a clear positive link.
3. **Our plain overnight spread does not reproduce the days.** The same dates replayed on real option prices (bull put and bear call, OTM1/OTM4, one lot, both exit times, both date readings) agree on sign 39% to 58% of the time, correlation between -0.16 and +0.31. Our one-lot totals on those days are within about +/-7,000 rupees. So whatever produces their numbers is not the simple structure we tested; it uses signals, strike choice, sizing or exits we cannot see.
4. **Repeated exact amounts.** -8,400 appears twice (2 Jun and 7 Jul), +22,860 twice (11 Jun and 23 Jul), -11,120 twice (24 Aug and 13 Oct), all with the same percentage. Live fills do not repeat to the rupee. That pattern fits rule-based simulated fills (a fixed stop or target price at fixed size). The screenshots do not say whether the tab is live or backtest, so this is a reason to ask Stratzy, not proof.
5. **The payoff shape is unusual for a credit spread.** Their average win is Rs 16.6k against an average loss of Rs 13.6k, with a 63% win rate. On real prices our overnight bull put and bear call have average wins well below average losses when the win rate is near 60% (about Rs 1.6k against Rs 3.1k at the close exit). Credit spreads normally win small and lose large, so a winner larger than the loser points to management or sizing we do not have.
6. **It trades about two days in three.** Tuesday 21, Thursday 20, Monday 16, Friday 7, Wednesday 3. A condition decides the days, as ours does, but it is not the 13-20 VIX band alone.
7. **Drawdown shown is about 10%**, and October 2026 is the first losing month on the page. Eight of the twelve October days lost.

What this does not prove: it does not show their numbers are wrong. It shows they cannot come from the published description (overnight spread, 3 PM exit, VIX 13-20) tested on real prices, and that the direction of the market does not explain them. The honest next step for a trader is to run Zen in Sandbox from Stratzy's own signals for a month and compare with the page, before putting money behind it.

## Decision

No change to the live engine. The two published differences do not pass the untouched period. The close-exit option stays research only in `run_lab(exit_field="close")`. The bull-put-only finding is a lead, not an edge: it breaks even before the last period turns it negative.
