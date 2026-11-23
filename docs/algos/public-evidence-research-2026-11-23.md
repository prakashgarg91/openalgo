# Public evidence on Nifty option edges (23 November 2026)

One Haiku 5.5 agent, read only (web search and fetch, nothing downloaded or run), asked after the GPT-6-Astra review.
Some sources were read from search snippets only (SSRN and MDPI pages refused the fetch). Nothing is adopted.

## 1. Volatility risk premium (implied above realised)
- Agarwal, "The Variance Risk Premium in Nifty 50", SSRN working paper 2026 (abstract 6530119): Aug 2022 to Mar 2026;
  the sign depends on the realised-volatility estimator (flips on 16.5 percent of days); no after-cost P&L. Low confidence, snippet only.
- subbu-31/nifty-short-premium-lab (MIT): 71 weeks, Jan 2025 to May 2026, one window, not out of sample. Implied
  above realised on 75.2 percent of days (mean +1.60 points). Costs took 31 to 60 percent of gross for condors and
  7 to 13 percent for strangles. Every structure lost net in the lowest India VIX third. Condor corrected p = 0.065.
  Raw data not included. Low to medium confidence; the most candid failure log found.
- Older India studies (NSE working paper 9/2013 and others): variance risk is priced, but monthly, pre-weekly, no costs.

## 2. Open interest and put-call ratio signals
- MDPI Economies 7(1):24, Nifty 2001 to 2013, rolling out-of-sample: no reliable short-horizon predictability. Medium confidence, snippet.
- A 2014 to 2020 study claims the highest-OI strike predicts the next close, but shows a price-level correlation, not a tested forecast. Low.
- OI and PCR dashboard sites: marketing, no validation.

## 3. Open platforms with honest results
- marketcalls/openalgo-execution-skills (MIT): Indian cost assumptions; no returns published.
- marketcalls/openalgo (AGPL-3.0): backtest reports by strategy family are listed; not opened, unverified.

## 4. Verified retail track records
- None found with broker-verified returns and drawdowns for retail Nifty option selling; only marketing and self-reported backtests.
- SEBI study (via secondary sources, check sebi.gov.in before quoting): about 87.7 percent of individual F&O traders lost
  money in FY26; most losses from options, many within a day of expiry. Medium confidence.

## What it means for 30 to 40 percent a year
No out-of-sample, broker-verified evidence supports it net of costs. The premium exists on paper but costs eat much of
it and it vanished in low-volatility periods in the one study that measured costs. Plan for flat or losing years and
size for the worst drawdown.

Note for later, not acted on: in that study the premium failed in LOW volatility, while our frozen rule skips HIGH
volatility (VIX 20 or more). This is an observation about a different study, not a reason to change a frozen rule;
any new gate would be a new pre-registered trial.
