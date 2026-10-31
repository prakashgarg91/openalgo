# Multi-horizon linkage study: registered 31 October 2026, before any result was computed

Why: the pair and chain studies looked one day ahead. A weekly credit spread lives for days to weeks, and what hurts it is a large move or a jump in volatility over that span. This study asks the same question over longer horizons, with longer lookbacks and with risk outcomes, not only direction. Nothing here is an expected profit.

## Unit and timing

One observation is an Indian trading day t, at the Indian close (10:00 UTC, 15:30 India). Every input is a bar that has ended by then. A bar's end is its stamp plus: 6.25 hours for Indian series, 8 hours for Asian series, 9 hours for European and US series (so the US session of day t, which ends after the Indian close, is not used), 24 hours for currencies and 23 hours for futures and commodities.

## Outcomes (starting after the close of t)

- ret5, ret20: Nifty log return over the next 5 and 20 trading days.
- lvol5, lvol20: log of the realised volatility of the Nifty over the next 5 and 20 days (square root of 252 over h times the sum of squared daily log returns).
- dd5: the worst cumulative log return from t's close at any close in the next 5 days (the downside a short put spread faces).

## Inputs

For each of the 108 series with a daily history (the context data, India VIX excluded as an input because its level is used in the baseline): the log return over the last 1, 5, 20 and 60 bars (a simple change for the three US yield series). Plus six derived inputs: US VIX over India VIX (level, log), the 10-year minus the 3-month US yield, the 20-day dollar-index return, the 20-day Brent return, India VIX level (ln), and the Nifty's own 20-day realised volatility. Pairs need 500 outcome days in each half.

## Split and tests

The same cut as the earlier studies (days to 19 July 2017 discover, the rest verify). Per pair: slope on a standardised input with a Newey-West t-statistic using 2h lags (10 for the 5-day outcomes, 40 for the 20-day outcomes, because outcomes overlap). Benjamini-Hochberg at 5 percent over every pair tried. Verified if the sign is the same and the t-statistic in the second half is at least 2 in size. Chance reference: the verification outcomes shuffled in blocks of 60 days, 300 times.

## Joint model

Ridge on all inputs fitted on the first half (penalty by time-ordered cross-validation inside it) and scored once on the second half by out-of-sample R-squared, against a baseline of India VIX level and the Nifty's own 20-day volatility and 20-day return. Reported for each outcome, with the gain over the baseline. Because outcomes overlap, a gain below 0.02 is treated as no gain.

## What would count

A verified pair with a written reason, and a joint gain over the baseline of at least 0.02 on an outcome. Even then it only becomes an input after improving a pre-registered rule on the option data. If nothing beats the baseline, longer horizons do not add information the volatility baseline lacks, and that is the finding.

## Limits

Overlapping outcomes mean far fewer independent observations than days (about 450 non-overlapping 5-day windows in all), so t-statistics are less reliable than the earlier studies even with the adjustment. Daily bars only. No news, flows, GIFT Nifty, intraday data. One regime split.
