# Rs 1,00,000 account, at most Rs 20,000 lost a day: what the engine found

Asked: test trading with Rs 1,00,000 and a Rs 20,000 daily loss limit, and have the engine find or
create an algo that earns better than Zen on bullish days, and the best for the other situations.

**Answer for option spreads: it found none that earns.** (Other algo families are in [universe-results.md](universe-results.md); one of them did earn after costs.)

**Option spreads:** On real option prices, after costs, on data it was not chosen on,
every candidate in the three searches lost money or showed no edge. The best available is to stand
aside, which is what the chooser does.

## How it was tested

- Real NSE option prices, January 2022 to October 2026 (1,188 trading days). Entry at the contract's
  close, exit at its open one to three trading days later. No option-pricing model.
- Costs: the Lab's itemised cautious costs (brokerage, taxes, exchange fees, bid-ask) on every candidate and on Zen.
- Account: Rs 1,00,000, one lot (75) at a time. A spread loses at most its width, so a 150-point spread
  risks Rs 11,250, under the Rs 20,000 cap. Wider spreads were excluded. Several algos on one day are held
  to the same cap by the runner (set `ALGO_MAX_DAILY_LOSS_INR=20000`).
- The search rules were fixed in `scripts/algo_backtest/mandate_search.py` before any result was seen:
  60 candidates per lean (strike shape x calm or calm+trending days x hold of 1, 2 or 3 days; credit and
  debit spreads), chosen on the first half of the trades, narrowed on the next quarter, and only the winner
  read on the last quarter (Aug 2025 to Oct 2026). An edge needs a profit factor of 1.2 and 1.35 on the two
  later periods with at least 40 trades each.

## Results

| Situation | Baseline | Candidates tried | Lost money on the untouched period | Verdict |
| --- | --- | --- | --- | --- |
| Bullish lean | Zen (bull put days): train about 0 per trade, then -321, then -446 | 60 (bull put and bull call debit) | 55 | No edge. Best found lost 11.1% of the account on the untouched period against Zen's 48.6%; still a loss. |
| Bearish lean | Zen (bear call days): -80, -215, -116 per trade | 60 (bear call and bear put debit) | 58 | No candidate traded often enough on the training period to judge. |
| Neutral | Calm Condor: -238, -375, -605 per trade | 30 (iron condors) | 30 | No edge. Best found lost 55.4% against the condor's 42.4%. |

The candidates that looked best in training (profit factor 8 to 9, bullish calm days held three days)
had 24 trades. They lost on validation and again on the untouched period. That is the shape of a lucky
result, not an edge.

## The account, whole real period (2022-01 to 2026-10), one lot, cautious costs

| Algo | Trades | Ended with | Worst day | Deepest fall | Daily Rs 20,000 limit |
| --- | --- | --- | --- | --- | --- |
| Zen, all days | 492 | Rs 6,510 (-93.5%) | -7,001 | -95% | never passed |
| Zen, bullish days | 407 | Rs 16,878 (-83.1%) | -7,001 | -85% | never passed |
| Zen, bearish days | 85 | Rs 89,632 (-10.4%) | -3,044 | -21% | never passed |
| Mirror Zen | 255 | Rs 34,332 (-65.7%) | -9,058 | -78% | never passed |
| Calm Condor | 237 | Rs 8,722 (-91.3%) | -4,172 | -91% | never passed |
| Do nothing | 0 | Rs 1,00,000 | 0 | 0 | never passed |

Zen by year, per lot: 2022 +11,972, 2023 -3,493, 2024 -40,176, 2025 -19,780, 2026 -42,013.

**Read this carefully.** The daily loss limit was never broken, because a defined-risk spread cannot lose
much in one day. That is not the risk. The account is lost slowly: more than half the trades lose, and costs of
Rs 200 to 450 a trade are larger than the edge before costs, which is about zero. The limit protects you
from one bad day, not from a strategy that loses a little every day.

## What this does not show

- It is Nifty index options held overnight or a few days. Intraday ideas, futures, other underlyings and
  stock options were not tested on real prices. A Rs 1,00,000 account cannot margin Nifty futures.
- The lot size is 75 as in the Lab; use your broker's current figure.
- Results depend on 2022 to 2026. A different era could differ; the one profitable year (2022) is in the
  training half and did not repeat.
- The search is a few hundred configurations. More trials raise the chance of a lucky winner, so none was added.

## Re-running it

```
uv run python scripts/algo_backtest/mandate_search.py <history_dir> <real_options_dir> bullish   # or bearish, neutral
uv run python scripts/algo_backtest/account_sim.py <history_dir> <real_options_dir>
```

Data comes from `fetch_history.py` and `fetch_nse_options.py`. In the app, the Lab's "Test on my account"
runs any algo through your capital and daily limit on modelled prices (which flatter option sellers).
