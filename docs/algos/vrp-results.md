# Variance risk premium test: results (run once, 31 October 2026)

Rules: [vrp-registration.md](vrp-registration.md), committed before this was computed. Code: `scripts/algo_backtest/vrp_study.py`. Table: private data repository, `research/vrp/summary.json`. 4,549 days; first half to 5 July 2017 (2,274 days), second half from 6 July 2017 (2,275 days). Payoffs below are in variance points times 10,000 (what a seller of 5-day variance at the VIX level would have kept; not a capped spread, no costs).

## The premium exists

India VIX stood above the volatility that followed on 78 percent of days, by 3.7 volatility points on average (4.1 in the first half, 3.2 in the second).

| Period | Days | Mean premium (vol points) | Mean payoff | t | Days positive | Worst 1 percent of days |
| --- | --- | --- | --- | --- | --- | --- |
| First half | 2,274 | 4.13 | 106.5 | 2.5 | 77% | -2,164 |
| Second half | 2,275 | 3.22 | 42.2 | 1.3 | 79% | -1,386 |
| All | 4,549 | 3.67 | 74.4 | 2.7 | 78% | -2,005 |
| All, without 1 Feb to 30 Apr 2020 | 4,491 | 3.85 | 94.0 | 4.2 | 79% | -1,673 |
| Second half, without that window | 2,217 | 3.56 | 81.2 | 7.3 | 80% | -731 |

The premium is positive in both halves, which met the first registered condition. But the second-half mean payoff is not statistically separate from zero (t = 1.3) with the Covid window in, and is strong (t = 7.3) without it. That is the shape of selling insurance: most days pay a little, and a few days take back many times the average. The worst 1 percent of days are 27 times the all-period mean in size.

## The gate did not work

The registered idea was to sell only when the expected premium (VIX minus a forecast of the volatility to come) is large. The forecast itself is good (out-of-sample R-squared 0.50 on the volatility that followed). Second half, by expected-premium group:

| Group | Days | Mean premium | Mean payoff | t | Worst 1 percent |
| --- | --- | --- | --- | --- | --- |
| 1 (lowest expected) | 649 | 2.87 | 57.5 | 2.8 | -1,347 |
| 2 | 665 | 2.94 | 48.1 | 3.8 | -567 |
| 3 | 508 | 2.99 | 15.8 | 0.3 | -1,075 |
| 4 | 309 | 4.12 | 55.2 | 0.8 | -587 |
| 5 (highest expected) | 144 | 5.00 | 12.2 | 0.1 | -8,877 |

Group 5 minus group 1: payoff -45 (t = -0.23). The registered condition (positive with t of at least 2) is not met, so no premium-based gate is offered to the option replay. The days that look richest on paper are the days where the biggest losses sit (worst 1 percent of group 5 is -8,877), which is the opposite of what a gate needs.

## What it means

1. Selling premium has had a positive average in India over 18 years, in both halves. That is consistent with the structure of every algo here, and it says nothing new about timing.
2. It is paid for with tail risk. A capped spread (400 points) truncates the tail; whether the cap and the stop leave a positive result after costs is what the option replay answers, and it is still the open question.
3. A "sell when the premium looks fat" rule does not work on this data. The range-group gate registered earlier, which stands aside on days predicted to be wide, is the remaining candidate.

## Limits

The VIX is a 30-day measure applied to a 5-day horizon; the payoff is a variance seller's with no cap, no costs and no skew; the Covid exclusion is reported both ways because it was registered as a reporting item, not chosen after seeing the result; one asset and one split.
