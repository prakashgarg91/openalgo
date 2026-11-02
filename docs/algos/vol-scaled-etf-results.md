# Volatility-scaled equity and gold: results (trial 320)

Registered in [vol-scaled-etf-registration.md](vol-scaled-etf-registration.md) before any code existed, and run once on 2 November 2026 on the Yahoo ETF closes (31 Oct 2011 to 30 Oct 2026) and the India VIX (to 29 Oct 2026). The report is `research/vol_scaled_etf/report.json` in the data repository. No parameter was changed after seeing a number.

## Verdict: rejected

The rule is: hold NIFTYBEES at 12 percent divided by a volatility forecast (never above 80 percent), split the rest equally between GOLDBEES and cash, decide at month-ends, trade at the next close. First decision 31 Jan 2013; 3,385 sessions.

| Gate | Result |
|---|---|
| 1. Ends above Rs 1,00,000 at normal and doubled costs | Pass (net +2,04,768 and +1,93,981) |
| 2. Drawdown and worst day within Rs 20,000 | **Fail** (drawdown 43,409; worst day -9,038) |
| 3. Beats the exposure-matched hold at both costs | **Fail** (behind by 79,813 and 90,493) |
| 4. Ahead of the matched hold in each half | **Fail** (-18,986 then -60,825) |
| 5. Bootstrap lower bound of mean monthly excess above zero | **Fail** (mean -484 a month, bound -1,236) |
| 6. Ahead without the best month | **Fail** |

## What it means in plain words

- The rule made money (about 8.4 percent a year) but less than simply holding the same average mix without trading it (the matched hold: 73.9 percent Nifty ETF, 13.2 percent gold, about 10.3 percent a year, net +2,84,581).
- It lost to that hold in 13 of 14 calendar years and beat it in 1.
- It cut the drawdown from 57,839 (matched hold) to 43,409, and the worst day from -13,116 to -9,038, so it does reduce risk. It does not reduce it enough to meet the Rs 20,000 limit, and it pays for the reduction with return.
- Costs were small (Rs 5,385 over 62 trading sessions at normal costs). The loss to the hold is the rule's timing, not its costs.
- Reference holds, at normal costs: 50/50 Nifty ETF and gold net +3,15,094 (drawdown 88,368); 40/40 with 20 percent cash +2,52,261 (drawdown 70,765).

## What was not reported

The registration also named a 100 percent NIFTYBEES hold as a reference. The run's output carries only the two holds above, so that figure is not in this report. It is not a gate and changes nothing.

## Consequence

Nothing goes forward: no shadow ledger and no registration for this idea. Trial 320 is used (running count 320). The next new idea slot is January 2027.
