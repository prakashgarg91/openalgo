# Outside research on what works (4 November 2026)

Gathered by three Haiku workers from public pages and checked by Sonnet only for consistency with our own results. Most primary PDFs could not be opened, so numbers are from abstracts and secondary summaries and are marked as unverified. Nothing here is investment advice, and nothing here is evidence about this platform's own strategies.

## MQL5 and retail algorithm sellers

- MQL5's own articles teach the same discipline this register uses: count how many settings were tried, keep a hold-out used once, test costs and slippage, use purged cross-validation (MQL5 articles 16957, 21603 and blog posts of 2026).
- A 2026 MQL5 blog argues signal rankings show survivors, not what a new subscriber should expect.
- No independent study of live results of MQL5 Market EAs or Signals subscribers was found.
- Retail loss studies: Chague, De-Losso and Giovannetti (SSRN 3423101) report 97 percent of persisting Brazilian day traders losing money; an Australian regulator report is quoted at about 68 percent of retail CFD clients losing (secondary).
- MetaTrader is mostly forex and CFDs; it does not trade Nifty options through Upstox.

## Strategy families (public evidence, none tested here on Indian data except where our own results say so)

| Family | What the evidence says | Why a retail account struggles |
| --- | --- | --- |
| Selling option volatility | Implied volatility has exceeded later realised volatility on average (AQR 2018, US data); losses cluster in crashes | Sized for the average month, not the crash; margin calls arrive when losses peak. Our own replays on weekly Nifty found no edge after costs |
| Trend following (time-series momentum) | Positive over decades and across markets (Moskowitz, Ooi, Pedersen 2012; Hurst, Ooi, Pedersen 2017) | Long flat stretches, a diversified futures set is hard to reach in India |
| Cross-sectional momentum, short-term reversal | Momentum has held up in reviews; reversal sits in small illiquid stocks | Turnover and bid-ask costs |
| Cash-and-carry (futures basis) | About 6 to 9 percent gross in Indian sources, small excess over a liquid fund after costs | Capital tied in margin; spreads shrink in corrections |
| Pairs and statistical arbitrage | About 11 percent a year on US pairs in 1962 to 2002 (Gatev et al.), decaying since (Do and Faff 2010) | Costs, shorting access, crowding |
| Volatility targeting | Improves risk control; does not reliably raise return (Moreira and Muir 2017 against Cederburg et al. 2020) | Using a risk rule as a source of profit |
| Overnight versus intraday | Anomaly returns split between overnight and intraday (Lou, Polk, Skouras 2019, US stocks) | Gap risk for a small average gain |

## India

- SEBI studies: about 91 to 93 percent of individual equity F&O traders lost money in each year studied (FY22 to FY25); a later summary gives 87.7 percent for FY26 (secondary, unverified). Transaction costs were 27 percent of gross losses in FY24 (Aggarwal and Mitra, Ideas for India, April 2026).
- Retail API trading needs a broker-registered static IP, changeable once a week; strategies under about 10 orders a second are generally not treated as algo orders. Confirm with the broker.
- The options STT of 0.15 percent on sale matches `services/algos/costs.py`. Nifty lot size is 65 on the 9 November 2026 chain.
- Arbitrage and liquid funds returned about 6.5 to 7.8 percent in 2026 (blogs): the hurdle any strategy here must beat after costs.

## What this means for the platform

- Keep the discipline: one registered idea a month, a forward test before money, count trials. Outside sources agree with it.
- The most defensible places to look next are not new option structures: they are risk-controlled ETF rules (already in the forward ledger), trend rules on liquid ETFs, and cash-and-carry as a low-return benchmark.
- The picker should keep showing costs, worst cases and past weeks, and should never present a fit score as a forecast.
