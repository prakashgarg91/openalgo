# Draft only: candidate for the January 2027 idea slot (17 November 2026)

Not registered, not frozen, not counted. Written so the owner can read it before deciding. Nothing here changes any platform behaviour.

## What the public source actually says

Source: the author's backtest at github.com/bHandreaPeR/nse-momentum-research (read 17 Nov 2026; not peer reviewed, no out-of-sample result, trade count not stated).

| Variant (March 2004 to November 2024, net of 25 bps a side and Indian tax) | CAGR | Sharpe | Deepest fall |
| --- | --- | --- | --- |
| Momentum, quarterly, 8-month trend filter | 16.2% | 0.60 | -27.3% |
| Momentum, always invested | 12.7% | 0.39 | -74.0% |
| Equal-weight top 200, buy and hold | 11.2% | 0.33 | -70.2% |

Reading it: most of the gain comes from the trend filter (move to cash when the market is below its 8-month average), not from stock picking. Momentum without the filter adds 1.5 points a year and still falls 74%. The filter is the same family as our six ETF trend ledgers already running forward, so this is probably not a new idea, and it would not need a new trial if it is one of those.

The author's own cautions: raw unadjusted prices, month-end data hides deeper falls, simplified tax, live results expected well below the backtest.

## Why the stock version does not fit Rs 1,00,000

About 40 stocks at roughly Rs 2,500 each, rebalanced quarterly: small tickets, wide spreads on lesser stocks, and 25 bps a side is likely too low there.

## What would fit

A single index ETF held while the index is above its 8-month average, otherwise cash. That is a plain trend rule on one instrument. Check first whether it differs from the existing ledgers c01 to c09 (docs/algos/etf-trend ledgers) in lookback or instrument. If it does not, do not register it: it would be a repeat.

## Data check

The private data repo (`openalgo-data/context/daily`) holds Nifty-constituent stocks, a few global ETFs, USDINR, VIX and index series, but no Indian momentum or low-volatility ETF history. Historify (DuckDB) was not opened in this pass. A momentum ETF test would need that history first.

## Decision for the owner

1. Do nothing in January and let the six trend ledgers and S3n finish. (Recommended: the research says every extra idea raises the bar for all of them.)
2. Or register one idea in January after confirming it differs from the ledgers.

Next free slot: January 2027.
