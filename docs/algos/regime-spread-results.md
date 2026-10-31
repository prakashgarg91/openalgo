# Regime-gated spread test: results (31 October 2026)

Rules: [regime-spread-registration.md](regime-spread-registration.md), committed before any option result was computed. Code: `scripts/algo_backtest/regime_spread_study.py`, `services/algos/regime_gate.py`, `services/algos/forward_shadow.py`. Tables: private data repository, `research/regime_spread/`.

## Verdict

**No cell qualifies and nothing is selected. All twelve cells lose money in the selection period and in the held-out third, before and after doubling the costs. The range gate does not rescue a Zen-style credit spread, and nothing goes to a forward shadow run from this test.**

## Data and split

108 expired weekly Nifty expiries from 3 October 2024 to 27 October 2026 (109 are listed by Upstox; 26 December 2024 returned no contract data on two attempts and is not in the set), 513 sessions. Selection: the first 342 sessions (26 September 2024 to 13 February 2026). Held out: the last 171 (16 February to 27 October 2026). Range groups over these sessions: group 1 on 365 days, group 2 on 87, group 3 on 44, group 4 on 16, group 5 on none. So the gates "skip group 5" and "groups 1 to 3" select the same days as "no gate" in effect, and only "groups 1 and 2" differs: six distinct cells, not twelve.

## Selection period (342 sessions)

Net result in rupees for one lot, after the conservative costs; the second figure doubles the costs.

| Side rule | Gate | Episodes | Net | At twice the costs |
| --- | --- | --- | --- | --- |
| A continuation | none, not5, g123 (identical) | 220 | -92,386 | -180,238 |
| A continuation | g12 | 214 | -108,327 | -194,754 |
| B opening-move fade | none, not5, g123 (identical) | 216 | -83,242 | -171,183 |
| B opening-move fade | g12 | 210 | -65,557 | -147,951 |
| C always calls | none, not5, g123 (identical) | 218 | -21,582 | -111,251 |
| C always calls | g12 | 212 | -18,499 | -105,462 |

A cell qualified only with at least 60 episodes and a positive result at twice the costs. None did (0 of 12), so no cell was selected. The gate on its own moved results by a few thousand rupees in either direction (it improved B and C and worsened A), with no consistent effect.

## Held-out third (171 sessions), descriptive only because nothing was selected

| Side rule | Gate | Episodes | Net | At twice the costs | Max drawdown | Worst day |
| --- | --- | --- | --- | --- | --- | --- |
| A | none, not5, g123 | 94 | -65,782 | -104,746 | 97,761 | -11,459 |
| A | g12 | 82 | -66,446 | -98,761 | 80,495 | -11,459 |
| B | none, not5, g123 | 96 | -59,811 | -101,213 | 72,675 | -10,840 |
| B | g12 | 84 | -65,287 | -98,356 | 72,163 | -10,840 |
| C | none, not5, g123 | 93 | -9,858 | -47,697 | 39,860 | -10,419 |
| C | g12 | 81 | -27,015 | -58,778 | 39,860 | -10,315 |

All 12 cells lost money in the held-out third. The registered limit was a drawdown of Rs 20,000; every cell exceeded it (the smallest, the always-call control, reached Rs 39,860). In both periods the control (always sell the call spread) lost the least; the two side rules that read the morning were worse. The side rules A and B have no value over the control here.

## A defect found, and a disclosed second run

The first run of this study (31 October, about 03:55 UTC) gave 22 to 55 episodes per cell in selection and one trade per cell in the held-out third, with "a position is still open" on 304 and 169 sessions. That was a defect in the replay, not a result. `forward_shadow.simulate_rule` treats an expiry-day exit as "the day is only partly stored" unless it falls at or after 15:29, a threshold for 1-minute candles; the 5-minute expired-contract bars end at 15:25, so every spread that reached expiry was treated as open for ever, which blocked every later entry. The fix adds a `last_bar` argument (default 15:29, so the forward shadow test on 1-minute candles is unchanged) and passes 15:25 for this study. After it the same cell closes 329 trades with none left open (37 before). The fix changes no entry, exit, cost or stop rule.

The registration said the held-out third would be replayed once. It was replayed twice: once under the defective machine, which produced at most one trade per cell and so carried almost no information about the held-out period, and once after the repair. The first run's tables are kept in the data repository as `selection_run1_defective.json` and `held_out_run1_defective.json`. The fix was made from the code path, before any corrected number was seen. Read the held-out figures with that disclosure. The result does not depend on it: nothing was selected, and all twelve cells lose in both periods.

## Trials counted

This test: 12 cells (6 distinct), one selection, one held-out replay under the corrected machine (and the defective first replay). With the earlier families (36 Zen cells, three side rules in the forward registration, linkage, chain, range, premium, horizon and momentum studies) the project's running count is large and almost nothing has survived the later period.

## What it means

1. A credit spread with Zen's structure (at the money, 400 points wide, entry at 10:15, stop 43.8 points then reverse) loses money on these 108 expiries whichever side rule is used, and standing aside on days predicted to be wide does not change that. The costs alone (conservative, about Rs 88,000 to 90,000 per cell over the selection period, the gap between the net and the twice-cost columns) are larger than the whole of the structure's pre-cost result. Before costs, in the selection period with no gate: rule A about Rs -4,500, rule B about Rs +4,700 and the always-call control about Rs +68,000 (net plus the cost implied by the two columns). So the side rules A and B earn nothing even before costs, and the control earns before costs what the costs then take back. Whether the conservative cost model is too harsh was not tested here and matters: costs of roughly Rs 270 a trade decide the sign.
2. The variance premium found on the long daily history is real, but this spread, with its stop-and-reverse rule, does not collect it after costs. The stop trades are where the money goes (167 of 329 trades in the control's selection period were stops).
3. The forward shadow test registered for 252 sessions starts from the same structure; this result gives no reason to expect it to pass, and it is now the only remaining test that uses new data.
4. What this does not cover: other structures (wider or narrower spreads, no stop, a different entry time, short strangles with defined risk, hold to expiry), real bid-ask fills, and anything outside 3 October 2024 to 27 October 2026, one falling-Nifty period.

## Limits

Candle fills with no bid and ask, a stop that assumes the worst high in a candle, one lot, one regime, 108 expiries (one listed expiry missing).
