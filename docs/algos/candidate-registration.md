# Twelve more ETF rules, registered before any forward day (30 October 2026)

Why: the owner asked for 10 to 20 algos built and tried. Each rule below is fixed here, runs as a shadow ledger beside ideas 1 to 3 from the first ledger day, and was also screened once on 15 years of history. The screening used data that was already examined, so it confirms nothing. Code: `services/algos/etf_candidates.py` (rules) and `services/algos/etf_ledger.py` (accounting, benchmarks); 26 tests. Accounting, costs, next-close trading, whole shares and the month-end trim to the cap are the ones in [idea-registration.md](idea-registration.md).

Nothing here places an order. Every rule invests at most Rs 80,000 in total (Rs 40,000 a sleeve where two are used).

## The rules

| # | Name | Rule |
| --- | --- | --- |
| c01 | trend200 | Nifty ETF while it closes above its 200-day average, else cash. Daily |
| c02 | cross50_200 | Nifty ETF while its 50-day average is above its 200-day average. Daily |
| c03 | absmom252 | At a month end, Nifty ETF if its 252-day return is positive, else cash |
| c04 | donchian55 | Buy the Nifty ETF on a close above the highest close of the previous 55 sessions; sell on a close below the lowest close of the previous 20 |
| c05 | rsi2_uptrend | Buy the Nifty ETF when the 2-day RSI is under 10 and it is above its 200-day average; sell when RSI is over 70 |
| c06 | gold_trend100 | Gold ETF while it closes above its 100-day average |
| c07 | voltarget | At a month end, Nifty ETF sized to Rs 80,000 times min(1, 0.12 divided by its 20-day annualised volatility) |
| c08 | drawdown_filter | Hold the Nifty ETF; leave when it closes 10 percent or more under its 252-day high; return when within 5 percent of that high |
| c09 | both_trend200 | Rs 40,000 sleeves in each ETF, each held while above its own 200-day average. Daily |
| c10 | inverse_vol | At a month end, Rs 80,000 split between the two ETFs in proportion to 1 over their 60-day volatility |
| c11 | dual126 | At a month end, the ETF with the higher 126-day return if positive, else cash |
| c12 | risk_off_to_gold | Nifty ETF while above its 200-day average; otherwise gold ETF while above its 200-day average; otherwise cash. Daily |

A held position whose signal is unchanged is left alone, and a position that has grown more than 5 percent past its cap is trimmed back at a month end.

## What counts as a result

- The benchmarks are the same as for ideas 1 to 3: half and half held, 40 and 40 with Rs 20,000 cash held, and for each rule a hold at that rule's own average exposure, with weights frozen from a replay of 18 January 2013 to 29 October 2026 before the first ledger day.
- A rule needs to beat its exposure-matched hold, not just cash or the fully invested hold, after costs and at double costs, with no simulated day lost over Rs 20,000.
- Fifteen ledgers are run together, so a win is judged at a one-sided 99.5 percent lower bound on the daily excess over the matched hold, and is reported against every trial in this project (150+ spread variants, 36 Zen cells, 48 daily-grid cells, 23 ETF rules, 15 ledgers screened here, the three Zen-style side rules, six registered ideas, and the Trading Rex agent's own 60 logged trials).
- The verdict is not due before 252 sessions. Until then these are SHADOW results, provisional, with splits and distributions not modelled.

## What the screening showed (development data, 13.8 years, Rs 1,00,000 each)

| Ledger | A year | Deepest fall | Charges | Hold at its exposure |
| --- | --- | --- | --- | --- |
| c01 trend200 | 3.9% | Rs 21,872 | Rs 12,167 | 7.3% |
| c02 cross50_200 | 3.3% | Rs 41,079 | Rs 2,556 | 6.9% |
| c03 absmom252 | 4.1% | Rs 31,819 | Rs 2,523 | 7.0% |
| c04 donchian55 | 2.4% | Rs 13,448 | Rs 7,734 | 5.6% |
| c05 rsi2_uptrend | -0.8% | Rs 27,118 | Rs 18,781 | 2.8% |
| c06 gold_trend100 | 4.9% | Rs 24,568 | Rs 14,902 | 6.4% |
| c07 voltarget | 4.8% | Rs 22,608 | Rs 6,449 | 7.1% |
| c08 drawdown_filter | 3.6% | Rs 19,594 | Rs 2,972 | 7.0% |
| c09 both_trend200 | 4.4% | Rs 13,881 | Rs 15,363 | 7.0% |
| c10 inverse_vol | 5.4% | Rs 19,237 | Rs 11,522 | 8.0% |
| c11 dual126 | 6.8% | Rs 23,859 | Rs 6,645 | 6.9% |
| c12 risk_off_to_gold | 5.1% | Rs 23,789 | Rs 21,129 | 7.9% |
| (hold half and half, fully invested) | 10.8% | Rs 87,874 | Rs 116 | |

None of the twelve beat the plain hold of the same average exposure, and none came near the fully invested hold's 10.8 percent a year. The closest was dual126 (6.8 against 6.9), which is the family found in 2026. In every case the smaller fall is mostly the smaller position. The daily rules pay Rs 12,000 to Rs 21,000 of charges over 13.8 years, which is what a 100-day or 200-day line costs in whipsaws. On this evidence the ETF family offers a smaller position, not better timing, and these ledgers are worth running only to see whether anything differs on days nobody has looked at.

## Limits

- The history is Yahoo's adjusted closes; the forward ledgers use raw closes.
- Nothing was tuned: every parameter above is a round number chosen before the screening run, and the screening was run once.
- No rule here is an option rule. Options ideas 4 to 6 in the idea registration still wait for data.
