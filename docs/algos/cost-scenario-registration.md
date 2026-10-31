# Retail-realistic cost scenario: registered 31 October 2026, before any recomputed number exists

Why: the regime-gated spread test ([regime-spread-results.md](regime-spread-results.md)) lost money in every cell under the project's conservative cost model, about Rs 270 a trade. An independent review (Opus 5.5, then checked against the code) found that model too low on fees and probably too high on slippage. The sign of the result depends on it. This page fixes a second cost scenario before it is applied, so it cannot be tuned until something wins. Nothing here is an expected profit.

## What does not change

Every entry, exit, stop, target and reversal. Costs are not part of any decision, so the trades are the same ones; only each trade's cost is recomputed. The same 12 cells (6 distinct), the same sessions, the same 342-session selection period and 171-session held-out third. All results are reported under both scenarios side by side.

## The scenario (per trade; a trade is one spread opened and closed, a reversal is another trade)

- Brokerage: Rs 20 per executed order, 4 orders per trade (two legs in, two legs out), so Rs 80. Source: the broker's published options fee (flat per executed order).
- STT: on the premium of the legs sold (the short leg at entry, the long leg at exit): 0.10 percent for a transaction dated before 1 April 2026, 0.15 percent from 1 April 2026 (Budget 2026 change, reported by several outlets; to be confirmed against the Finance Act text).
- Exchange transaction charge: 0.0345 percent of premium turnover (all four fills), as in the existing model. Not independently verified; small.
- SEBI turnover fee: Rs 10 per crore of turnover, 0.0001 percent.
- GST: 18 percent of brokerage plus exchange charge plus SEBI fee.
- Stamp duty: 0.003 percent of the premium of the legs bought (the long leg at entry, the short leg at exit).
- Slippage: 0.15 points per fill, 4 fills per trade, every fill including a stop exit (the exit rule's own 2-point stop slip stays, as part of the frozen exit). This figure is an assumption, not a measurement: liquid Nifty weekly options usually quote about 0.1 point wide at the money, and wider away from it. It is replaced by measured bid and ask data from the snapshots described in [bid-ask-snapshots.md](bid-ask-snapshots.md) when about 60 sessions exist, and that, not this number, decides any further scenario.
- Lot size: 75 before 30 December 2025 and 65 from that date, for profit and for cost (the old model used 75 for cost throughout).
- The twice-cost column doubles the whole total.

## What will be reported

For every cell, net under the conservative model and under this scenario, for the selection period and the held-out third, with episodes, drawdown and worst day. A cell is a candidate only under the original rule (at least 60 episodes in selection and a positive result at twice the realistic costs).

## What a result means

The held-out third has already been seen, twice, so nothing here can pass a test. A cell that turns positive under the realistic scenario is a hypothesis for the forward shadow test on new days, not a finding. If every cell stays negative the structure does not pay even at realistic costs. No further cost scenarios will be added after the numbers are seen; a third is allowed only if measured bid and ask data says the slippage assumption is wrong, and it is then registered before it is applied.

## Limits

Candle fills, not executable prices. The slippage assumption dominates the result: at 0.15 points it is about Rs 45 a trade, so a result that flips on it is fragile. One falling-Nifty period.
