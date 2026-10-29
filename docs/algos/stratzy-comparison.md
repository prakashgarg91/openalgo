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
| Follow lean, exit open, VIX 13-20 (see correction below) | -48,549 | 42% | +5,491 | -28,152 | -25,888 |
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
4. **Repeated exact amounts.** -8,400 appears twice (2 Jun and 7 Jul), +22,860 twice (11 Jun and 23 Jul), -11,120 twice (24 Aug and 13 Oct), all with the same percentage. The trade table behind this page (below) explains it: the stop is a fixed 43.1 points over the credit, filled at exactly the trigger price, with the same 3 lots both times. The feed marks every trade as executed and none as backtest, but a stop that fills at the trigger to the paisa is how a simulated or idealised fill behaves, so the page does not show what a live account would have received.
5. **The payoff shape is unusual for a credit spread.** Their average win is Rs 16.6k against an average loss of Rs 13.6k, with a 63% win rate. On real prices our overnight bull put and bear call have average wins well below average losses when the win rate is near 60% (about Rs 1.6k against Rs 3.1k at the close exit). Credit spreads normally win small and lose large, so a winner larger than the loser points to management or sizing we do not have.
6. **It trades about two days in three.** Tuesday 21, Thursday 20, Monday 16, Friday 7, Wednesday 3. A condition decides the days, as ours does, but it is not the 13-20 VIX band alone.
7. **Drawdown shown is about 10%**, and October 2026 is the first losing month on the page. Eight of the twelve October days lost.

What this does not prove: it does not show their numbers are wrong. It shows they cannot come from the published description (overnight spread, 3 PM exit, VIX 13-20) tested on real prices, and that the direction of the market does not explain them. The honest next step for a trader is to run Zen in Sandbox from Stratzy's own signals for a month and compare with the page, before putting money behind it.

## Zen's rules, reverse-engineered from its own trade table

The Rex repository (`trading-rex-ai`) holds a capture of the full published trade list: 204 trades from 2025-07-09 to 2026-08-28 with sold and long strike, credit, exit debit, lots and entry and exit times (research note `RESEARCH-stratzy-zen-past-trades-analysis.md`, taken from Stratzy's public Past Trades feed, all trades marked executed, none backtest). The table is not copied into this repository. The screenshots above are the same data: the calendar date is the exit date. Script: `scripts/algo_backtest/stratzy_zen_reverse.py`; output in `stratzy-zen-reverse-output.txt`.

| Question | What the table shows |
| --- | --- |
| Width | Exactly 400 points on all 204 trades. Ours is 150. |
| Sold strike | At the money: median 15 points from that day's open, middle half from 70 points in to 53 out. Ours is one strike out. |
| Which expiry | The nearest weekly, on every day of the weekly cycle: 0 or 1 days to expiry on 67 trades, 4 to 6 days on 116. |
| Size | 2 to 6 lots (mostly 4 or 5), chosen to fill a fixed Rs 3.2 lakh allocation: lots equal the allocation divided by margin per lot. |
| Entry time | 10:15 to 10:35 on 163 of 204 trades. Never at the close. |
| One at a time | It is in one position at a time and enters the next 10:15 after it is flat. |
| Days it stays out | When India VIX is 20 or higher it entered 31% of flat sessions at VIX 20 to 25 and 17% above 25, against 85% to 100% below 17; and after a gap down of 1% or more (22%). Median VIX on its trade days is 12.2, 90th percentile 18.2. So "VIX 13 to 20" is really a ceiling near 20; most trades are at VIX 11 to 14. |
| Stop | The spread's value rises 43.8 points over the credit (middle half 41.9 to 46.3, 89 stops), the same distance whatever the credit or lots. Roughly Rs 2,900 per lot. |
| After a stop | It reverses: 59 re-entries came within 4 hours of an exit, 85% of them after a stop, and 73% switched side. |
| Exit | 15:00 or 14:53 the next session on 73 trades, 09:15 or 09:16 next morning on 23 (gap exits), at expiry on 7, and 47 closed at a debit of 12 points or less (a target near 10 points). |
| Side (put or call) | Not recoverable. Put share is 60% when the day closes above its open and 44% below; 57% after a gap up and 47% after a gap down; 47% with the prior close above its 20-day average and 57% below. All weak. |
| Real prices | The published credit sits inside the exchange's real price range for that spread within 10 points on 74% of trades and within 25 on 87%. The entries are consistent with real prices. |
| Which side earned | Bear call trades: 98 trades, +Rs 6.15 lakh. Bull put trades: 106 trades, +Rs 1.32 lakh. About 82% of the profit came from calls. It is not a bullish algo. |

Correction to the earlier section: the "VIX 13 to 20" test above required VIX of at least 13, which removed most of Zen's real trades. It tested the wrong filter.

## Does that structure earn on daily real prices?

1. **On Zen's own entries, a plain hold works a little.** Entering at the published credit and simply closing at the next session's close, with no stop and no target, earns +1,492 points against the published +2,469 (60% of it), with a 66% win rate. After conservative costs that is +995 points, 4.9 points per trade, about Rs 320 per lot per trade. The stops and targets added +977 points in 2026 and nothing in the second half of 2025 (886 published against 967 for a plain hold). The 79 stops averaged -48.9 points against -56.5 for a plain hold.
2. **The rule is not recoverable from daily data.** A pre-registered grid of 48 variants (shape, side rule, VIX filter, expiry rule) entered at the close and held to the next close: 33 of 48 lost money in 2025-26. One cell was positive in all three periods (400 wide, at the money, follow the day's direction, Zen filter): +172k, +8.5k, +27k, and -27k inside Zen's own window, with a worst drawdown near Rs 1.1 lakh for one lot. One survivor in 48 tries is what chance produces.
3. **An artefact that would have fooled us.** Entering at the opening print made the "follow the gap" rule look like +7.7 lakh and its reverse like -8.1 lakh, stable across years. It is not real. Options' first trade of the day lags the gapped spot: put-call parity is off by about +46 points after a gap down and -28 after a gap up at the open, and flat at the close. Selling the side the gap favours therefore sells a stale, too-high print that nobody could trade. Any test using bhavcopy opening prices has this flaw.

What cannot be done here: Zen's edge, if it exists, sits in the 10:15 entry and the 43-point stop with reversal, and testing it needs intraday option prices for expired contracts. Those come from Upstox's paid Plus plan (5-minute bars, expired-instrument endpoints) and are not stored in either repository. The Rex repository already has `UpstoxExpiredDataSource` for it.

## What differs from ours, in one list

| | Zen (from its table) | Ours |
| --- | --- | --- |
| Width | 400 | 150 |
| Sold strike | At the money | One strike out |
| Entry | About 10:15 | Close of the previous session |
| Exit | 15:00 next session, or stop, or target near 10 points | Next morning at about 09:45 |
| Stop | Fixed 43 points over the credit, then reverses | None; stops are percent of premium in the live engine only |
| Volatility rule | Stays out at VIX 20 or more and after a 1% gap down | Regime label, no VIX ceiling |
| Size | Fills a Rs 3.2 lakh allocation (4 to 5 lots) | One lot |
| Risk seen | Worst published trade -Rs 66.7k on 5 lots (10 April to 13 April 2026 gap), 1 lot about -Rs 13.3k | Capped by the 150 width |

On a Rs 1 lakh account with a Rs 20k daily cap, Zen's structure fits only at one lot, where the worst published loss was about Rs 13.3k.

## Decision

No change to the live engine. The two published differences do not pass the untouched period, and the structure reverse-engineered from the trade table cannot be tested fairly without intraday option prices. The close-exit option stays research only in `run_lab(exit_field="close")`. The bull-put-only finding is a lead, not an edge: it breaks even before the last period turns it negative.

## Zen's rules on real 5-minute option prices (run 2026-10-29)

Data: Upstox Plus expired-contract history, 70 weekly Nifty expiries, 4,185 contract files, 328 sessions from 1 July 2025 to 27 October 2026. Run with `scripts/algo_backtest/stratzy_zen_intraday.py`; method in [intraday-test.md](intraday-test.md). Nothing was ordered.

### Part 1: do the exit rules reproduce Zen's published trades?

The 204 published entries were replayed with the 43.8-point stop, the 10-point target and the 15:00 next-session exit. 201 could be priced from the bars.

| | Published | Replay |
| --- | --- | --- |
| Points, 201 trades | 2,191 | 2,569 |
| Points per trade | 10.9 | 12.8 |
| Win rate | 56% | 54% |
| Stops | 97 | 83 (78 of them on the same trades) |

Correlation per trade is +0.91 and the total is 17% above the published one, so the check (correlation 0.8 or more, total within 25%) passes. Entry credit from the bars is within 5 points of the published credit on 65% of trades (median error 2.9 points). The replay is kinder than the published fills by about 2 points a trade, so any result below is, if anything, flattering.

What this proves: the exit rules (stop, target, next-session exit) behave like Zen's on Zen's own entries. It does not prove anything about how Zen chooses the side, which is the part we cannot see.

### Part 2: 36 pre-registered cells, one lot, conservative costs

Six side rules (always put, always call, follow the previous close, follow the morning move, lean, flip) by three exit styles (stop and reverse, stop only, no stop) by two filters (none, or VIX under 20 and no 1% gap down). Totals are Rs per lot over the whole window; thirds are the first, middle and last third of the period.

| Side rule | Exit | Filter | Total | Thirds |
| --- | --- | --- | --- | --- |
| put | stop+reverse | none / zen | -159,141 / -105,894 | -1,963, -82,931, -74,248 / -1,963, -28,079, -75,852 |
| put | stop only | none / zen | -200,167 / -156,199 | 548, -134,618, -66,097 / 548, -93,889, -62,858 |
| put | no stop | none / zen | -170,980 / -151,722 | -940, -123,494, -46,546 (both) |
| call | stop+reverse | none / zen | -12,292 / -10,450 | 16,678, -5,519, -23,451 / 16,678, 1,167, -28,294 |
| call | stop only | none / zen | +31,622 / +61,860 | 38,714, -3,454, -3,638 / 38,714, 31,627, -8,481 |
| call | no stop | none / zen | +92,817 / +118,495 | 28,794, 43,730, 20,293 / 28,794, 69,408, 20,293 |
| follow previous close | stop+reverse | none / zen | -80,962 / -58,628 | 34,552, -40,808, -74,705 / 34,552, -13,631, -79,549 |
| follow previous close | stop only | none / zen | -70,837 / -14,381 | 61,538, -74,203, -58,172 / 61,538, -12,903, -63,016 |
| follow previous close | no stop | none / zen | -93,866 / -32,247 | 55,046, -60,873, -88,040 / 55,046, 747, -88,040 |
| follow morning move | stop+reverse | none / zen | -176,468 / -146,593 | -17,092, -56,094, -103,282 / -17,092, -21,375, -108,126 |
| follow morning move | stop only | none / zen | -139,998 / -102,813 | -10,663, -57,100, -72,234 / -10,663, -15,072, -77,078 |
| follow morning move | no stop | none / zen | -164,340 / -131,694 | -9,982, -76,798, -77,560 / -9,982, -44,152, -77,560 |
| lean | stop+reverse | none / zen | -47,892 / -4,129 | 32,884, -36,350, -44,427 / 32,884, 9,018, -46,031 |
| lean | stop only | none / zen | -62,154 / -25,204 | 30,943, -62,202, -30,896 / 30,943, -28,490, -27,658 |
| lean | no stop | none / zen | +18,524 / +29,295 | 76,879, -55,938, -2,418 / 76,879, -45,166, -2,418 |
| flip | stop+reverse | none / zen | -88,745 / -50,800 | -19,167, -56,519, -13,059 / -19,167, -5,669, -25,964 |
| flip | stop only | none / zen | -166,688 / -58,550 | -9,500, -115,566, -41,622 / -9,500, -34,730, -14,320 |
| flip | no stop | none / zen | -218,417 / -116,375 | -7,857, -152,968, -57,593 / -7,857, -50,926, -57,593 |

Count: 36 cells tried, 34 lost money in the last third. Two were positive in all three thirds: always sell the call spread with no stop, with and without the Zen filter.

### What the two survivors are, and why they are not an edge

- They sell a call spread every day and hold it to the next session. Nifty fell 10.9% over this window (25,542 to 22,753), so selling the side a falling market does not touch pays. That is a view on direction, not a rule.
- With the Zen filter: 175 trades, mean +Rs 677 per trade, t-statistic 1.84. Without: 188 trades, mean +Rs 494, t-statistic 1.29. Neither reaches the usual 2.
- Two of 36 cells being positive in every third is within what chance gives when cells are this correlated.
- The worst single trade was -Rs 18,296 (-Rs 16,785 with the filter), against a daily limit of Rs 20,000 on one lot. A single gap would use almost all of the loss budget.
- Adding the stop makes the same call rule worse (the stop trades are where the money goes), which is the opposite of what Zen is meant to do.
- All 12 stop-and-reverse cells (Zen's actual structure, both sides) lost money in the last third, by between Rs 13,059 and Rs 108,126.

### What cannot be known from this run

- How Zen picks the side. The exit rules reproduce; none of our six side rules does. If Zen's side choice has an edge, it is not among these six.
- Real fills. Bars have no bid or ask, the stop is filled at the trigger plus 2 points, and a live market stop would be worse.
- Inside a 5-minute bar. The stop assumes the worst high; the target needs the close.
- Anything outside 1 July 2025 to 27 October 2026, and only one market regime (a falling Nifty).
- Untouched data: all 36 cells were run once on the full window and reported in thirds. There is no separate holdout beyond the last third, so a rule picked from this table would need new data before it is trusted.

### Verdict

No rule earns after costs in a way that survives. The exit rules of Zen are real (they reproduce), but run as Zen runs them, with any of the six side rules we could write down, the result lost money in the last third. The Zen in the catalogue is not changed.
