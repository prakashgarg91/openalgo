# Regime-gated spread test: registered 31 October 2026, before any option result was computed

Question: does standing aside on days the range model ranks as wide improve a Zen-style credit spread after costs, on the 109 expired weekly expiries? Inputs and their reasons: [range-model-results.md](range-model-results.md) (the baseline range model ranks days well; direction from foreign markets does not verify). This page fixes the test before any option candle was replayed. Nothing here is an expected profit and nothing is traded.

## Data

`openalgo-data/bars5m` (5-minute candles of expired weekly Nifty options, 3 Oct 2024 to 27 Oct 2026, a window with one broadly falling Nifty), Nifty 1-minute index candles from Upstox for the same days (`openalgo-data/index`), and India VIX daily from `context/daily`. Only expiries listed complete in `MANIFEST.csv` are used.

## Frozen entry and exit machine

The one in `services/algos/forward_shadow.py` (version 2026-10-29-v1): at the money, 400 points wide, entry at 10:15, stop 43.8 points over the credit then reverse, target near 10 points, exit at 15:00 next session, no entry when India VIX of the previous session is 20 or higher or after a 1 percent gap down, conservative costs, candle fills. Side rules A (continuation), B (opening-move fade) and C (always calls) are the registered ones from [forward-test-registration.md](forward-test-registration.md).

## The gate (the only thing varied)

The range group of day D is the baseline model (ln India VIX of D-1 and the Nifty range of D-1), coefficients and group cut points fitted on 4 March 2008 to 10 July 2017 only and frozen (the same fit as model 1 in the range study). Groups 1 to 5 are by predicted range, lowest to highest. Four gates:

- none: every day (the ungated control)
- not5: skip group 5
- g123: trade only groups 1 to 3
- g12: trade only groups 1 and 2

Twelve cells: four gates by three side rules. All twelve are tried and all are reported.

## Procedure

1. Sessions are ordered and cut into thirds. The first two thirds are the selection period; the last third is held out and is not replayed until the selection is written to a file.
2. Selection period: all twelve cells are replayed. Candidates need at least 60 completed episodes and net profit above zero at twice the costs. Among candidates the one with the highest net profit is selected. If none qualifies, nothing is selected and that is the finding.
3. Held-out third: the selected cell is judged once. Pass requires all of: at least 30 completed episodes; net profit above zero after costs and at twice the costs; maximum drawdown marked to market no more than Rs 20,000; no day losing more than Rs 20,000; a 97.5 percent one-sided lower bound above zero for the mean daily result by a moving-block bootstrap (block of 5 sessions), and the same bound above zero for the paired daily difference against the ungated cell of the same side.
4. The other eleven cells are also reported for the held-out third, marked descriptive; none of them can pass.

## Reporting

Trials: twelve cells; the 36 earlier Zen cells and the three side rules of the forward registration are part of the same family and are counted in the write-up. Report, for every cell, episodes, net, net at twice the costs, drawdown, worst day, and how many cells lost money in the held-out third. Report any expiry that could not be used and why.

## What a pass means

Only that the gated cell goes to a forward shadow run on new days under a new registration, in sandbox mode. It is not an expected profit and does not change the catalogue. A fail ends this branch of work.

## Limits

One market regime (a falling Nifty), about 500 sessions, candle fills with no bid and ask, and a stop that assumes the worst high inside a candle.
