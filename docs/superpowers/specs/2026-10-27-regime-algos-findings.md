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
algos enter.** It is knowable by 09:00 to 09:15. Algos that use foreign cues
properly should enter in the morning, after the gap is visible. That is the next
algo to build, not a tuning of these three.

## What to do next, in order

1. Run all three in Sandbox mode for at least a month and read the Sandbox
   record on the page. Sandbox fills are idealised, so this is a floor.
2. Add a morning-gap algo that enters after 09:15 using the opening gap and the
   overnight US move, and test it the same way before enabling it.
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
