# Intraday momentum on the Nifty: results (run once, 31 October 2026)

Rules: [intraday-momentum-registration.md](intraday-momentum-registration.md), committed before this was computed. Code: `scripts/algo_backtest/intraday_momentum_study.py`. Table: private data repository, `research/intraday_momentum/summary.json`. Run once on the local computer after the Nifty 1-minute file was extended back to 3 January 2022 (447,292 candles).

## Sample

1,107 sessions, 3 January 2022 to 30 October 2026. The first half (553 to 554 sessions) is discovery, the second half is verification and was scored once. The registration expected about 520 sessions; the extension doubled that. India VIX from the context data defines volatile days; the expiry flag is the weekly calendar rule (Thursday before 1 September 2025, Tuesday after); holiday shifts are not modelled, so a few expiry sessions are mislabelled.

## Counts

- Pairs tested: 12 (three predictors, four conditions). All are reported below.
- Selected in discovery (t of 2 or more in size): 1 (calm days, first half-hour).
- Verified (same sign in both halves and t of 2 or more in size in the second half): 0.
- Joint model of the last half-hour on all three predictors, second half: R-squared -0.028, which is worse than predicting the average.

## All twelve pairs

Slope of the last half-hour return on the predictor, Newey-West t-statistic (5 lags).

| Condition | Predictor | First half beta (t) | Second half beta (t) | Verified |
| --- | --- | --- | --- | --- |
| all | first30 | -0.051 (-1.11) | 0.036 (1.31) | no |
| all | prev30 | 0.015 (0.19) | -0.139 (-1.76) | no |
| all | gap | 0.011 (0.54) | -0.025 (-1.06) | no |
| volatile | first30 | -0.034 (-0.51) | -0.001 (-0.02) | no |
| volatile | prev30 | 0.023 (0.22) | -0.232 (-2.62) | no |
| volatile | gap | 0.013 (0.50) | 0.004 (0.26) | no |
| calm | first30 | -0.073 (-2.36) | 0.084 (1.91) | no |
| calm | prev30 | 0.038 (0.40) | 0.006 (0.08) | no |
| calm | gap | 0.005 (0.21) | -0.082 (-2.11) | no |
| expiry | first30 | -0.020 (-0.38) | 0.034 (0.72) | no |
| expiry | prev30 | 0.122 (1.07) | -0.116 (-0.63) | no |
| expiry | gap | 0.048 (1.29) | -0.047 (-2.94) | no |

## What this says

- No pair verified. The one pair that looked real in the first half (calm days, first half-hour, t of -2.36) reversed its sign in the second half (beta +0.084, t of +1.91). That is the signature of noise.
- Three pairs reached a t-statistic of 2 or more in size in the second half (volatile prev30, calm gap, expiry gap), and each had the opposite sign or no effect in the first half. With twelve tests, one or two such values are expected by chance alone.
- The first half-hour momentum published for the S&P 500 (it predicts the last half-hour, more on volatile days) is not present on the Nifty in 2022 to 2026. The slope is not stable in sign.
- The joint model fails out of sample. Nothing here is usable as a rule, and nothing goes to the option replay.

## Limits

About 4.8 years of sessions. A weak test of a small effect: a true effect of one tenth of the published size would not have been found. No costs, one market, index prints only (no cash-market closing auction detail). Three of the twelve conditions rest on fewer than 250 second-half sessions.

## What failed

Everything: no pair verified, and the joint model is below zero. The registered claim, that early-session momentum predicts the last half-hour on the Nifty, is not supported.

## Trials counted

One study, 12 pairs, one joint model. Added to the project's running count with the linkage studies (see [SESSION_MEMORY.md](SESSION_MEMORY.md)).
