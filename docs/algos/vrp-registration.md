# Variance risk premium test: registered 31 October 2026, before any result was computed

Question: does India VIX, on average, exceed the volatility that the Nifty then delivers, and does that gap predict how well selling option premium would have done? This is the structural question behind every credit spread in this project. See [literature-notes.md](literature-notes.md). Nothing here is an expected profit.

## Data

`openalgo-data/context/daily`: `_INDIAVIX.csv` (close, annualised percent) and `_NSEI.csv`. Days from the start of India VIX (March 2008). Split as in the earlier studies: fitted on the first half (to 10 July 2017), scored once on the second half.

## Definitions (day t, known at the close)

- IV(t) = India VIX close / 100.
- Forward realised volatility over the next 5 trading days, RV5(t) = sqrt(252 / 5 x the sum of squared Nifty close-to-close log returns on t+1 to t+5).
- Premium(t) = IV(t) - RV5(t). Variance payoff proxy(t) = IV(t)^2 - RV5(t)^2 (what a seller of 5-day variance at the VIX level would have kept; it ignores the 30-day tenor of the VIX, costs and the spread's cap).
- HAR forecast of RV5 at t: ordinary least squares of RV5 on yesterday's, the 5-day and the 20-day realised volatility, fitted on the first half only. Expected premium(t) = IV(t) - HAR forecast(t). Quintile cut points come from the first half.

## Tests, reported in full

1. Mean premium and mean payoff proxy, with a Newey-West 10-lag t-statistic, in each half and overall. Share of days with a positive premium. The worst 1 percent of payoffs.
2. By expected-premium quintile, in the second half: mean premium, mean payoff proxy, share positive, and the worst 1 percent. Quintile 5 minus quintile 1 payoff with a Newey-West t-statistic.
3. How much of the 2020 crash window (1 February to 30 April 2020) drives the mean: results with and without it.

## What would count

A premium that is positive in both halves, and a quintile 5 minus quintile 1 payoff that is positive with t of at least 2 in the second half. Then the gate "trade only when the expected premium is in the top groups" is offered as a candidate for the option replay. If the premium is not positive in the second half, or the quintile spread is not, that is the finding: nothing here says selling premium pays in India on a 5-day horizon.

## Limits

The VIX is a 30-day measure and the weekly options are shorter; the payoff proxy is a variance seller's, not a capped spread's; no costs, no skew; one asset, one regime split.
