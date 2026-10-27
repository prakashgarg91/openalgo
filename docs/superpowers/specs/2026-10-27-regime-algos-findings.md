# Regime algos: readiness findings

Date: 2026-10-27. Companion to
[`2026-10-27-regime-algos-design.md`](2026-10-27-regime-algos-design.md).

## Verdict

The platform side is built and tested: catalogue, regime scoring, daily entry,
Sandbox-first deployment, a Live gate, a decision log. **Profit in every season
and condition is not demonstrated, and should not be promised.** One algo
(Mirror Zen, as first defined) lost money in the indicative test. The other two
looked good in a test that is known to flatter them.

## How it was tested

`scripts/algo_backtest/` runs the real `score_regime` and `build` from the repo
over Nifty, India VIX, S&P 500, Nasdaq, crude and dollar index history from
2018 to October 2026 (2,146 trading days). Each day's regime is computed from
the same inputs the live runner uses, the algo's legs are priced with
Black-Scholes using India VIX as flat volatility, entry is the close, exit is
the next open, and costs are Rs 300 per lot per trade.

Not modelled: stop losses and targets, volatility skew, real bid-ask on far
strikes, margin, expiry shifts on holidays, the real 09:45 fill. The test is a
sanity check on the rules, not a forecast of returns.

## Results (regime-gated, per lot of 75, after costs)

| Algo | Trades | Won | Profit factor | Deepest drawdown | Worst trade |
| --- | --- | --- | --- | --- | --- |
| Zen | 1,360 | 62.5% | 1.49 | Rs 49,656 | Rs 8,312 |
| Mirror Zen | 701 | 41.8% | 0.79 | Rs 1,06,283 | Rs 5,367 |
| Calm Condor | 659 | 60.2% | 5.77 | Rs 6,670 | Rs 6,457 |

## What the test says

1. **Mirror Zen as defined loses money in every regime.** Fading the market's
   lean with a credit spread lost on calm, trending, volatile and event days
   alike. It is marked Experimental in the catalogue.
2. **Bear call spreads lost in every regime; bull put spreads made money.** The
   sample was mostly a rising market, so selling puts harvested drift as well
   as premium. This says nothing about a falling market, which is not in the
   sample in any depth.
3. **The directional lean is not shown to help.** When the lean was bearish,
   selling puts still beat selling calls. The bias that picks Zen's side has no
   demonstrated predictive value yet.
4. **Standing aside is a risk choice, not a profit choice.** Ungated Zen made
   money on volatile and event days too (profit factor 1.38 and 1.13). The
   gate gave up about Rs 94,000 per lot over the period. It did not reduce
   Zen's deepest drawdown (about Rs 49,500 either way). It did help the condor
   (drawdown Rs 6,670 gated against Rs 13,845 ungated).
5. **The condor result is too good to trust.** A profit factor near 6 with a
   tiny drawdown is what a flat-volatility model gives a premium seller.
   Expect real results to be much lower.
6. **2026 is a warning.** Zen lost about Rs 44,000 per lot in 2026 while the
   calm-market condor still made money in the model.

## Coverage by market condition

| Condition | Covered? | Notes |
| --- | --- | --- |
| Calm | Zen, Calm Condor | Best evidence, still model-based |
| Trending up | Zen (bull put) | Worked in the sample |
| Trending down | Zen (bear call) | Lost in the sample; no good answer yet |
| Volatile (VIX over 20, big US move) | Stands aside | About 19% of days |
| Event day (gap over 1.2%, VIX over 28) | Stands aside | About 17% of days |
| Scheduled events (budget, policy, results, elections) | Not modelled | No event calendar yet |
| Sustained bear market | Not tested | Not in the sample |
| Overnight US moves | Not knowable at entry | See below |

## A design limit worth knowing

Zen, Mirror Zen and Calm Condor enter at 15:05 IST and hold overnight. The US
session, and any overnight news, happens after entry. The regime can only use
the previous US close, so **foreign-market impact cannot be known when these
algos enter.** It is knowable by 09:00 to 09:15. The obvious next step was a
morning algo that waits for the gap. It was built and tested; see the next
section for why it is not a recommended strategy.

## Morning-gap research (day 4)

Question: do the opening gap and the overnight US move predict how the day
plays out after the open? If they do, a morning algo has something to trade. If
they do not, no option structure will rescue it.

Method (`scripts/algo_backtest/signal_power.py` and `run_morning_gap.py`): the
same 2018 to October 2026 data, split into a train period (2018 to 2022) and a
test period (2023 onward). The rule is chosen on the train period only and
judged on the test period. Always-sell-puts and always-sell-calls baselines show
whether any gap logic adds anything over plain premium and drift.

Results:

| Measure | Train | Test |
| --- | --- | --- |
| Mean open-to-close move | -0.076% | -0.039% |
| Share of days up (open to close) | 48.4% | 47.0% |
| Correlation, gap vs rest of day | -0.03 | -0.07 |
| Correlation, US move vs rest of day | -0.04 | -0.06 |
| Correlation, US move vs the gap itself | +0.50 | +0.41 |
| Day moves the same way as a big US move | 49.4% | 46.2% |

- **The open already holds the foreign-market move.** The US move and the gap
  move together (+0.4 to +0.5). After the open, neither predicts the day: the
  hit rates are coin flips and the correlations are slightly negative.
- **No candidate rule made money.** Of the signal rules tried (fade the gap,
  follow the gap, follow it only when the US agrees, fade it when the US
  disagrees), none with 150 or more train trades had a positive total on the
  train period. On the test period none of the rules with 80 or more trades had
  a profit factor above 1.0.
- **The baselines lose too.** Always selling puts intraday had a profit factor of
  0.39 on train and 0.47 on test; always selling calls 0.60 and 0.59. Intraday
  spreads earn little time decay in six hours against about 4 points of costs.
- **Index return sat overnight in this sample.** Nifty averaged +0.10% overnight
  and -0.06% from open to close. That favours holding positions overnight (what
  Zen does) and argues against opening new ones in the morning.

Decision: **no morning-gap rule has an edge, so it is not recommended.** The
rule that ranked best on the train period alone was fading gaps of 0.75% or more
(profit factor 0.67 on 163 train trades). On the test period it scored 0.47 on
62 trades and lost money in each of 2023, 2024, 2025 and 2026. It is shipped as
**Morning Gap Fade, Experimental**, because it was asked for and because the
Sandbox record is the honest way to study it, with the evidence on its card. The
Live gate means it cannot go Live without earning a profitable Sandbox record.

What this does not show:

- Not tested: stops and targets, volatility skew, the real intraday path, other
  structures (debit spreads, straddles), or other instruments such as Bank Nifty.
- The VIX "open" in the free data equals the previous close 97.8% of the time, so
  the entry volatility is stale. This does not bias the direction of the
  result, but it makes the pricing less exact.
- The test period has 940 days and the winner only 62 trades, so the test figure
  for the shipped rule is itself noisy. The finding that no rule beat the
  baselines, and that the cues do not predict the day, does not depend on it.

What did come out of it: each algo now has its own check time, and the feed
carries the opening gap, so a future morning algo is a template and not a
rebuild.

## What to do next, in order

1. Run all three in Sandbox mode for at least a month and read the Sandbox
   record on the page. Sandbox fills are idealised, so this is a floor.
2. Do not build more algos on the opening gap or the overnight US move; the
   research above found no edge. Better candidates to test the same way (train
   and test, with baselines) are a different instrument, a different structure,
   or a rule that manages the overnight position using the morning gap.
3. Add an event calendar so budget, policy and election days are stood aside on
   by date, not only after the gap appears.
4. Replace Mirror Zen's definition with something that survived the test, or
   remove it. Do not tune the three algos until the numbers look good: with
   this much freedom that is overfitting.
5. Go Live only with small capital, after a Sandbox record that passes the
   gate, and on the understanding that the worst case shown on the page is the
   number to plan around.

## Rerun it

```
uv run python scripts/algo_backtest/fetch_history.py <data_dir>
uv run python scripts/algo_backtest/run_backtest.py <data_dir>
```
