# Multi-horizon linkage study: results (run once, 31 October 2026)

Rules: [horizon-study-registration.md](horizon-study-registration.md), committed before this was computed. Code: `scripts/algo_backtest/horizon_study.py`. Tables: private data repository, `research/horizon/`. 4,573 days; discovery to 19 July 2017, verification after. Inputs known at the Indian close; outcomes over the next 5 and 20 trading days.

Two small deviations from the registration, stated here: 288 inputs entered (series with fewer than 500 days in each half drop out of every pair), and the two derived inputs for the 20-day dollar and Brent returns were not added separately because those series are already in the grid at the 20-day window; four derived inputs were used (India VIX level, US VIX over India VIX, 10-year minus 3-month yield, the Nifty's own 20-day volatility). 1,420 pairs tried.

## Counts

| Outcome | Selected in discovery | Verified in the second half |
| --- | --- | --- |
| Return over the next 5 days | 2 | 0 |
| Return over the next 20 days | 1 | 0 |
| Volatility over the next 5 days | 180 | 165 |
| Volatility over the next 20 days | 67 | 24 |
| Worst fall within the next 5 days | 10 | 1 |
| All | 260 | 190 |

Shuffling in 60-day blocks, 5.5 percent of the selected pairs would verify by luck (95th percentile 15.8 percent); 73 percent did. The links are real as a group, and almost all of them are about volatility.

## Direction: nothing, at any horizon tested

Out of 1,420 pairs only three found anything in the first period for the 5-day and 20-day returns, and none verified. The joint model of all 288 inputs has an out-of-sample R-squared of -0.5 percent for the 5-day return and -0.4 percent for the 20-day return: no better than guessing the average. Foreign markets, sectors, stocks, currencies, commodities, yields and their trailing 1-, 5-, 20- and 60-day moves do not predict where the Nifty goes over the next week or month in this data.

## Volatility: predictable, but the baseline already has it

The volatility of the next 5 days is strongly tied to India VIX (t = 15 in the second half) and the Nifty's own recent volatility (t = 7), and then to recent price falls: stronger trailing returns of the Nifty, Sensex, Bank Nifty, sectors and heavyweights go with lower volatility ahead (slopes near -0.2 per standard deviation, t from -4 to -6), and a steeper US yield curve goes with higher. That is the known pattern that falls raise volatility.

The joint model does not improve on its simple baseline (India VIX level, the Nifty's own 20-day volatility and 20-day return):

| Outcome | R-squared, baseline | R-squared, all 288 inputs | Gain |
| --- | --- | --- | --- |
| Return, 5 days | -0.1% | -0.5% | -0.4% |
| Return, 20 days | 0.2% | -0.4% | -0.6% |
| Volatility, 5 days | 55.3% | 48.8% | -6.5% |
| Volatility, 20 days | 63.6% | 56.2% | -7.4% |
| Worst 5-day fall | 7.1% | 5.1% | -2.1% |

The registered test needed a gain of at least 2 points over the baseline. Every gain is negative: adding the other markets makes the forecast worse out of sample, which is what overfitting looks like. The three-number baseline is the answer.

## What it means

1. A longer horizon does not open a hidden predictor of direction. Combined with the one-day and chain studies, no market in this data predicts the Nifty's direction in a way that survives the later period, at horizons from the open to a month.
2. Volatility is the one thing that is predictable, and the three-input baseline captures nearly all of it. Extra markets add noise.
3. What the volatility signal is worth to a credit spread is not shown here. The variance premium test found the premium exists but its gate failed; the range-group gate on the option data is what remains.

## Caveats

Overlapping outcomes leave about 450 independent 5-day windows, so t-statistics are less reliable even with the lag adjustment. Daily bars, no news, flows or GIFT Nifty, one regime split. A very long trailing window (60 days) mixes the 2008 and 2020 crises into the first half. Inputs and outcomes were fixed before the run and nothing was tuned afterwards.
