# Range model: registered 31 October 2026, before any result was computed

Why: the linkage study ([linkage-study-results.md](linkage-study-results.md)) found that direction after the open is not predictable from foreign markets, but the day's range is, mostly from India VIX and the Nifty's own recent range. A credit spread's stop and strike distance depend on the range. This page fixes a better range model and how it will be judged. Nothing was computed when it was written.

## Target

ln(range) of the Nifty day D, where range = (high - low) / open. Data: `openalgo-data/context/daily`, same days and the same split as the linkage study (fit on 4 March 2008 to 19 July 2017, score once on 20 July 2017 to 29 October 2026).

## Inputs, all known at the Nifty open of D

- vix_prev: ln of India VIX close of D-1
- vix_open: ln of India VIX open of D
- range_1, range_5, range_20: Nifty range of D-1, mean range of the last 5 days, mean of the last 20 days
- abs_gap: absolute gap of D (open over previous close)
- us_vix: ln of the US VIX close of the previous US session (timing rule as in the linkage study)
- weekday: four dummies

## Models (ordinary least squares, fitted on the first half only)

1. Baseline from the linkage study: vix_prev, range_1
2. Baseline plus vix_open
3. Baseline plus range_5, range_20
4. Baseline plus abs_gap
5. Baseline plus us_vix
6. Full: all inputs

Six models are tried and all six are reported. The primary one is model 6.

## Scoring (second half, once)

- Out-of-sample R-squared on ln(range) against predicting the first-half mean, and rank correlation.
- Calibration: days are ranked into five equal groups by predicted range using cut points from the first half only; the mean realized range of each group is reported, and the ratio of the top group to the bottom group.

## What would count

Model 6 must beat model 1 out of sample on both R-squared and rank correlation, and the calibration must rise from the lowest to the highest group. Only then is a predicted range offered to the algos as an input (for stop width, strike distance and standing aside). It still has to improve a pre-registered spread rule on the option data before any algo uses it. If not, the baseline stays and that is the finding.

## Not in this study

Intraday data, news, flows, direction. Weekly expiry day effects are only through the weekday dummies.
