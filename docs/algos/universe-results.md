# Beyond Zen: every algo family that fits Rs 1,00,000 and a Rs 20,000 daily loss limit

Asked: not just Zen, find or create the best algo among all the kinds of algo in the market.

**Short answer.** Option spreads (Zen, Mirror Zen, Calm Condor and 150 variants) lose money after costs on real
prices ([mandate-results.md](mandate-results.md)). The one family that earned after costs on years it was not
chosen on is **rotating monthly between a Nifty ETF, a gold ETF and cash**. Its edge over simply holding half
Nifty and half gold is small, so most of what it earns is owning equities and gold, not timing skill.

## What was searched

23 rules, fixed in `services/algos/universe.py` before any result was seen:

| Family | Rules | What it does |
| --- | --- | --- |
| Trend filter | 4 (50, 100, 150, 200-day average) | Hold the Nifty ETF while it is above its average, else cash |
| Momentum rotation | 6 (63, 126, 252 days; one ETF or split) | Each month hold what rose over the last N days (Nifty ETF or gold ETF), else cash |
| Short-term mean reversion | 6 | Buy a sharp dip inside an uptrend, sell the bounce |
| Seasonal | 7 (turn of the month x2, each weekday x5) | A calendar rule |

Judged against two bars every investor already has: **cash at an assumed 6 percent**, and **buying and holding the
Nifty ETF**. Data: 15 years of daily closing prices (Oct 2011 to Oct 2026) of NIFTYBEES and GOLDBEES. The history was
cut into chosen-on (2012 to Nov 2019), checked-on (to May 2023) and never-seen (May 2023 to Oct 2026). A rule
shows an edge only if it beat cash on both later periods AND either beat buy and hold or kept most of its return
with a much shallower deepest fall, and no day lost more than the Rs 20,000 limit.

Every trade is made at the close a full day after its signal. Costs are itemised (brokerage, exchange, stamp, tax,
depository, slippage). They are assumptions: check them against your broker.

## Result

The search chose **dual momentum, 126-day, one ETF** (hold whichever of the Nifty ETF and gold ETF rose more over
126 trading days, if it rose; else cash). On the never-seen period:

| Never-seen period (May 2023 to Oct 2026) | Return a year | Deepest fall | Worst day |
| --- | --- | --- | --- |
| Dual momentum (126, one ETF) | 15.7% | Rs 25,800 | Rs 10,517 |
| Buy and hold Nifty ETF | 7.8% | Rs 16,229 | Rs 3,134 |
| Half Nifty ETF, half gold ETF held | 14.5% | Rs 18,723 | Rs 5,591 |
| Cash (6%) | 5.6% | 0 | 0 |

Rs 1,00,000 on that period: dual momentum ended at about Rs 1,64,000, buy and hold Rs 1,29,000. The Rs 20,000
daily limit was never passed.

Of the 23 rules, 11 earned less than cash on the never-seen period. All five weekday rules, both turn-of-the-month rules and four of the six
mean-reversion rules lost to cash. Trend filters earned modestly with a shallower fall (the
100-day one: 8.3 percent a year, deepest fall Rs 8,687 against buy and hold's Rs 16,229), so a trend filter is the
quieter alternative.

## How honest is that result

- **Most of it is gold.** Gold ETF rose about 4.4x over the 15 years and sharply in the last years. A static half
  and half hold, with no timing at all, earned 14.5 against 15.7 percent on the never-seen period and ended the whole
  period at Rs 2,59,708 against the rotation's Rs 2,96,758 (fixed Rs 1,00,000 base, not compounded). The timing adds
  about one percent a year.
- **In the chosen-on years it did not beat buy and hold** (7.7 against 9.4 percent a year). It earned its place on
  the later years.
- **It loses in some years:** Rs -6,331 (2013), -14,127 (2018), -10,751 (2022), -5,790 (2024) per Rs 1,00,000.
  Position changes: 43 in 14.7 years; costs Rs 6,921 in total.
- The neighbouring settings (63 and 252 days, splitting between ETFs) also earned more than cash on the
  never-seen period, so it is a plateau and not a single lucky setting. That is not proof.
- It is one never-seen period of 3.5 years, with a gold rally in it. No forecast follows from it.

## What could not be tested, and why

- **Gap and overnight rules**: they need the opening price. The free ETF opening prints are unreliable (an open of
  146 on a day that closed at 126), so such a test would measure data errors. Rules here use closing prices only.
- **Stock picking and momentum across shares**: only today's index members are available free, which makes
  every result look better than it was (survivorship bias). It is not offered.
- **Futures**: a Nifty future's margin is more than Rs 1,00,000.
- **Intraday option ideas**: no intraday option history.

## Data problems found on the way (so they stay found)

The first run showed a 97 percent yearly return and a Rs 89,984 loss in one day. It was bad data: Yahoo showed the
ETFs at a tenth of their price on 19 and 20 December 2019, and many opening prices were wrong. The cleaner now drops any
close more than 35 percent from the median of the closes around it, whatever the length of the streak; tests cover it.
Cleaned ETF returns match the Nifty index (0.97 daily correlation, similar total return).

## Using it

- **In the app:** Algos, Build your own, "Search every kind of algo" runs the search with your capital and daily
  limit (needs internet, about 20 seconds).
- **As a strategy:** `strategies/examples/etf_momentum_rotation.py` for the Python page. It acts on the first trading
  day of each month at about 15:15 IST, defaults to DRY_RUN (prints the orders it would place), and keeps its own
  record so it never sells what it did not buy. Run it in Sandbox first. It has not been run against a broker;
  the calls follow the installed SDK. Its decisions are tested to match the tested rule exactly.
- **From the command line:**

```
uv run python scripts/algo_backtest/fetch_etf.py <dir>
uv run python scripts/algo_backtest/universe_search.py <dir>
uv run python scripts/algo_backtest/universe_detail.py <dir>
```

## What you must still decide

Whether to own gold and equity ETFs on a Rs 1,00,000 account at all. The daily limit is about size: an ETF fully
invested can fall several percent in a day, and in March 2020 the Nifty ETF fell 10 percent in one day (Rs 10,000
on this account). The assumed 6 percent on idle cash needs a place to earn it (a liquid fund or overnight fund).
