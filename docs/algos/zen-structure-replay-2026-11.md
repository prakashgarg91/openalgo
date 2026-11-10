# Zen-shaped credit spread on all our option candles (10 November 2026)

Question: Zen's side-picking rule cannot be recovered, so does a fixed Zen-shaped spread (at the money, 400 wide, entered 10:15, held about a day, stop at 1.5 times the credit, target at 69 percent captured) earn on our own candles, each side alone? Script: `scripts/algo_backtest/zen_structure_replay.py`. Rules were fixed in the script before any result was read. One lot, our realistic costs and double costs, every session as a separate trade (trades overlap, so drawdown is overstated against a one-position book). Per-trade rows and summary are in the private data repo, `research/zen_structure_replay/`.

Trial count: 4 cells (two sides, with and without the VIX 20 gate) are added to the running count (321 reserved for Zen calls only, so 325). This is a screen, so the older months are the only unseen part for the rule's own design; they were still looked at together with the rest.

## Result (net after costs, rupees, one lot)

| Cell | Oct 2024 to Jun 2025 | Jul 2025 to Oct 2026 | All | Win rate | Deepest fall (all) |
| --- | --- | --- | --- | --- | --- |
| Call spreads, no gate | +84,894 (151) | +165,606 (258) | +250,501 (409) | 64% | 66,633 |
| Call spreads, VIX gate | +102,372 (146) | +171,926 (242) | +274,298 (388) | 64% | 66,633 |
| Put spreads, no gate | -67,510 | -278,782 | -346,292 | 55% | 349,286 |
| Both sides | +17,385 | -113,176 | -95,791 | 59% | 238,468 |

Call spreads at double costs: +186,812 (no gate) and +214,506 (gate), still positive.

## Reading

- Call spreads earned in both periods and in 9 of 10 quarters of the window; put spreads lost in both. Zen's own mix of both sides lost on our data in the window, yet its real record made money, so its side choice adds something we have not captured.
- Nifty rose 1.1 percent in the earlier months and fell 10.7 percent after. Call spreads earned in both, which is less regime dependent than first feared, but only two market stretches exist, and 2025 Q4 lost Rs 22,565.
- Overlapping trades: Rs 66,000 deepest fall and worst day near minus Rs 18,000 are above the Rs 20,000 cap in some runs, so one lot of every session is more than the account should carry.
- This is a screen on data we have studied. It earns the call-spread idea a forward shadow ledger, not money. The Zen calls-only follow ledger and this rule are close to the same idea.
