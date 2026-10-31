# Range model: results (run once, 31 October 2026)

Rules: [range-model-registration.md](range-model-registration.md), committed before this was computed. Code: `scripts/algo_backtest/range_model.py`. Table: private data repository, `research/range_model/summary.json`.

4,554 days. Fit on 4 March 2008 to 10 July 2017, scored once on 11 July 2017 to 29 October 2026. Six models tried.

| Model | R-squared out of sample | Rank correlation |
| --- | --- | --- |
| 1 baseline (India VIX of D-1, range of D-1) | 0.551 | 0.537 |
| 2 plus India VIX open of D (stale, see note) | 0.551 | 0.537 |
| 3 plus 5- and 20-day mean range | 0.553 | 0.541 |
| 4 plus absolute gap | 0.552 | 0.541 |
| 5 plus US VIX | 0.548 | 0.543 |
| 6 full | 0.547 | 0.547 |

## Verdict on the registered test

Not met. The full model has a higher rank correlation than the baseline (0.547 against 0.537) but a lower R-squared (0.547 against 0.551), and the registered test needed both. Calibration does rise from the lowest to the highest group, so the model ranks days well:

| Predicted range group | Days | Mean realized range |
| --- | --- | --- |
| 1 (lowest) | 1,080 | 0.82% |
| 2 | 441 | 1.07% |
| 3 | 374 | 1.20% |
| 4 | 288 | 1.45% |
| 5 (highest) | 94 | 2.97% |

The top group's range is 3.6 times the bottom group's. The group sizes are uneven because the cut points come from the first half (2008 to 2017, which holds the 2008 crisis); the second half was calmer, so most days fall in the lower groups.

## What it means

- The baseline stays: India VIX of the previous day and the previous day's range already carry what this data can say about the range. A VIX opening print, a gap, longer averages, the US VIX and the weekday add nothing out of sample.
- The ranking is real and large, so it is a usable input as it stands: stand aside or widen the stop on days in the top group (the 2.97% days are the ones that stop out a 43.8-point spread), and trade the lower groups. Whether that improves a spread rule is tested on the option data, not here.
- One regime split (2008 to 2017 against 2017 to 2026) is what was tested; a different split could give different group sizes.

## Correction, 31 October 2026

Model 2 added the India VIX open of day D. The data check done for the domino chain test found that this open equals the previous close on about 90 percent of days in the Yahoo series, so model 2 did not test a real VIX open. Its result (no change) says nothing about whether the VIX open helps; that remains untested and needs intraday VIX bars (about two years are available at one hour). The other five models and the verdict on model 6 are unaffected.
