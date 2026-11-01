# Alternative structures: results (1 November 2026, run once)

Rules: [structures-registration.md](structures-registration.md), committed before any structure was replayed. Code: `services/algos/condor.py`, `scripts/algo_backtest/structures_study.py`, `services/algos/costs.py`. Tables: private data repository, `research/structures/`. Same 108 expiries and 513 sessions as the earlier tests, first 342 sessions for selection, last 171 for the held-out third (already seen twice, so it cannot pass anything new). Costs are shown under the earlier cost model and the retail-realistic scenario ([cost-scenario-results.md](cost-scenario-results.md)); "at twice" doubles the realistic costs. One lot, rupees.

## Verdict

**No structure passed. S2 (weekly condor) and S4 (late condor) lose money and are dropped. S1 and S3, the two that sell only calls, made money under every cost scenario in both periods and were candidates, but both failed the drawdown limit and the statistical test in the last third, so neither is promoted by this registration.**

## Selection period (342 sessions)

| Structure | Trades | Before costs | Earlier cost model | Realistic costs | At twice the costs | Worst drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S1 call spread, 250 wide, no stop | 191 | +69,013 | +10,599 | +38,498 | +7,984 | 50,265 |
| S2 weekly condor | 68 | +339 | -25,996 | -19,873 | -40,084 | 57,776 |
| S3 weekly call spread | 67 | +70,732 | +50,045 | +60,033 | +49,335 | 31,881 |
| S4 condor, entered 14:30 the session before | 68 | -9,834 | -28,623 | -29,261 | -48,687 | 61,994 |

Candidates (at least 40 trades and a positive result at twice the realistic costs): S1 and S3.

## Last third (171 sessions), the candidates judged, the others descriptive

| Structure | Trades | Before costs | Earlier model | Realistic | At twice | Worst drawdown | Worst day |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 87 | +66,566 | +40,076 | +52,956 | +39,346 | 26,601 | -9,786 |
| S2 | 30 | +16,068 | +2,907 | +7,273 | -1,523 | 32,968 | -22,165 |
| S3 | 30 | +77,873 | +68,857 | +73,189 | +68,504 | 26,723 | -13,352 |
| S4 | 29 | +23,867 | +15,775 | +15,844 | +7,821 | 17,210 | -12,159 |

Registered gates for S1 and S3: at least 20 trades (met), positive at realistic costs (met), positive at twice the costs (met), worst drawdown no more than Rs 20,000 (**failed**: 26,601 and 26,723), no day losing more than Rs 20,000 (met), and a bootstrap lower bound above zero for the mean daily result at the level corrected for four structures (**failed**: the bound is -127 a day for S1 and -74 for S3). Passed: none.

## What it says

1. **Dropping the stop and the reversal changed the picture.** The earlier test lost money on every variant because the stop-and-reverse rule paid for almost every trade; on 250-point call spreads without a stop, the same data earns Rs 38,000 to Rs 60,000 before the last third's Rs 53,000 to Rs 73,000, and stays positive at twice the realistic costs.
2. **It is a call-selling result.** The two winners sell only calls. The weekly condor, which adds a put side, earned almost nothing before costs (+339 in selection) and loses after them: the put side gave back what the call side earned. S4 lost in selection too. The earlier finding stands in a new form: in this window the only thing that paid was selling upside, which is a view that the Nifty does not rally hard.
3. **By trailing market** (sign of the Nifty's return over the 20 sessions before entry), realistic net, selection period: S1 +57,314 after non-falling stretches and -18,815 after falling stretches; S3 +74,090 and -14,056. So the profit was earned after flat or rising stretches and given back in part after falls, when rebounds hurt a short call. This does not support the simple reading that it only works because the market fell, and it does not clear it either; it is one window.
4. **The loss limit is the binding problem.** The best structures draw down Rs 26,000 to Rs 32,000 on one lot, more than the Rs 20,000 a day limit and about a third of the account. With the Rs 1 lakh account, one lot of these structures is already too big for the risk rule.
5. **The statistical bound fails.** Daily results are large and uneven, and a 34-week held-out third cannot show that the mean is above zero. A profit of Rs 53,000 to Rs 73,000 over 171 sessions was not enough to clear the corrected bound.

## What this means for the next step

- Nothing is promoted by this registration, and no structure is a finding. S1 and S3 are hypotheses for the forward shadow ledger on new days, nothing more. The held-out third was already seen, so there is no clean data left in this window.
- A smaller version of S1 or S3 (for example fewer lots, a narrower wing, or a hard stop at a fixed loss) might meet the Rs 20,000 drawdown limit, but that is a new variant. It must be registered before it is run, counted as a new trial, and cannot be chosen using the last third.
- The bid and ask snapshots now matter more: the slippage assumption sits under every figure above.
- Trials counted: these four, with the 12 spread cells, the 36 earlier Zen cells, the three forward rules and the research families before them.

## Limits

Candle fills with no bid and ask; one window in which the Nifty fell overall; selling only calls leaves unlimited-in-spirit upside risk capped here only by the 250-point wing; the condor pairs two spreads priced from separate candles; S1's trades overlap overnight; the held-out third had been seen twice.
