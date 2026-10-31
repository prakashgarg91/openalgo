# Linkage study: registered 31 October 2026, before any result was computed

Question: which foreign markets, commodities, currencies, Indian sectors and Nifty heavyweights move before the Nifty, and by how much? The answer will set which inputs the algos may use to change their weights. This page fixes the method. Nothing was computed when it was written. Data: `openalgo-data/context/daily` (Yahoo, 110 series). Nothing here is an expected profit.

## Unit and timing

- One observation is an Indian trading day D (a Nifty daily bar). Its information time is the Nifty open, 03:45 UTC (09:15 India).
- A series bar is usable for D only if its end time is at or before that open. End time is the bar's stamp plus 24 hours for currencies, 23 hours for futures, commodities and the dollar index, and 9 hours for everything else (all stamps are session opens in UTC). Taking the latest such bar and the one before it gives the feature. This keeps the US close of the previous evening, European and Asian closes of the previous day, and the previous Indian close; it drops the same-day Asian and European sessions.
- Feature = log return of that bar (simple change for the three US yield series). Extra baseline features: ln India VIX of D-1, and the Nifty's own range of D-1.
- Targets for D: gap (open over previous close), intraday return (close over open), range ((high - low) over open), close-to-close return.

## Split

All days from the start of India VIX (March 2008) to 29 October 2026 are ordered and cut at the middle day. The first half is discovery; the second half is verification and is not looked at until the discovery list is written to a file. Every feature-target pair with at least 500 observations in each half is tried. The number of pairs tried is reported.

## Discovery (first half only)

- Per pair: slope, and a t-statistic with a Newey-West variance (5 lags).
- Selection: Benjamini-Hochberg with false-discovery rate 5 percent across every pair tried.
- Pairs are kept only with their sign.

## Verification (second half, once)

- A selected pair is verified if its sign is the same and its t-statistic is at least 2.0 in size.
- Chance reference: the same selected pairs are scored against the verification targets shuffled in blocks of 20 days, 1,000 times; the share that would verify by luck is reported next to the real share.
- Also reported: how many selected pairs flip sign.

## Joint model (does the whole picture predict, out of sample)

Ridge regression on all features, penalty chosen only inside the discovery half by time-ordered cross-validation, then scored once on the verification half: out-of-sample R-squared and rank correlation, against a baseline that uses only the two baseline features. One model per target.

## What would count

Only a pair that verifies, and whose effect has a one-line economic reason, is a candidate input for an algo. A candidate still has to improve a pre-registered spread rule on the option data before it changes anything, and then runs forward in sandbox mode. If almost nothing verifies, or the joint model does not beat its baseline, that is the finding.

## Not in this study

News, FII and DII flows, GIFT Nifty and other things that cannot be timed or fetched; domino chains through several steps (reported only after pair links exist); anything intraday.
