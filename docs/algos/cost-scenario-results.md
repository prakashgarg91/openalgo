# Retail-realistic cost scenario: results (31 October 2026)

Rules: [cost-scenario-registration.md](cost-scenario-registration.md), committed before any recomputed number existed. Code: `services/algos/costs.py`, `scripts/algo_backtest/regime_spread_recost.py`. Tables: private data repository, `research/regime_spread/recost.json` and `recost_selection.json`. The trades are the same ones as in [regime-spread-results.md](regime-spread-results.md); only the cost of each was recomputed. Cost per trade: about Rs 155 under the realistic scenario against about Rs 265 to 300 under the conservative one.

## Result in one line

The verdict stands. No cell qualifies. Under realistic costs the always-sell-calls control turns positive, but it does not survive doubling the costs, it breaches the loss limit by a wide margin, and rules A and B lose even before costs.

## Selection period (342 sessions), one lot, rupees

| Cell (no gate unless stated) | Episodes | Before costs | Conservative net | Realistic net | Realistic at twice the costs | Worst drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| A continuation | 220 | -4,534 | -92,386 | -56,509 | -108,484 | 75,245 |
| A, two calmest groups | 214 | -21,900 | -108,327 | -72,940 | -123,979 | 91,676 |
| B opening-move fade | 216 | +4,699 | -83,242 | -45,947 | -96,592 | 122,887 |
| B, two calmest groups | 210 | +16,838 | -65,557 | -31,308 | -79,454 | 108,248 |
| C always sell calls | 218 | +68,086 | -21,582 | +16,970 | -34,147 | 57,148 |
| C, two calmest groups | 212 | +68,464 | -18,499 | +18,660 | -31,144 | 51,079 |

The no-gate, skip-group-5 and groups-1-to-3 cells are identical here (no session fell in group 5), as before. Qualifying cells under the registered rule (at least 60 episodes and positive at twice the realistic costs): none. Nothing is selected.

## Held-out third (171 sessions), descriptive only

| Cell | Episodes | Before costs | Conservative net | Realistic net | At twice the costs | Worst drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| A | 94 | -26,818 | -65,782 | -48,171 | -69,524 | 81,465 |
| A, two calmest | 82 | -34,131 | -66,446 | -52,448 | -70,765 | 67,897 |
| B | 96 | -18,409 | -59,811 | -39,970 | -61,532 | 55,228 |
| B, two calmest | 84 | -32,218 | -65,287 | -50,362 | -68,507 | 57,396 |
| C | 93 | +27,982 | -9,858 | +7,611 | -12,760 | 36,175 |
| C, two calmest | 81 | +4,748 | -27,015 | -13,031 | -30,809 | 36,175 |

## What it says

1. **Rules A and B have no edge.** They are flat to negative before any cost in the selection period and clearly negative before costs in the held-out third. Costs are not what sinks them.
2. **The control is positive only under realistic costs, and thinly.** Always selling the call spread earns Rs 17,000 over 342 sessions and Rs 7,600 over the last 171 under the realistic scenario. Doubling those costs turns both negative, so the result sits on the slippage assumption (0.15 points a fill), which is an assumption and not a measurement. Selling the two calmest groups only did not help.
3. **It is a bet on a falling market.** The one thing that ever paid was selling calls while the Nifty fell. That is direction, not collected premium, and this window fell.
4. **The risk limit is breached by every cell.** The worst drawdown of even the best cell was Rs 36,000 in the held-out third and Rs 57,000 in selection, against a Rs 20,000 limit for the whole account.
5. **Nothing here can pass.** The held-out third has been seen twice, and the realistic scenario was registered after the conservative results were known. Treat the control's positive result as a hypothesis for new data only.

## What changes next

The slippage assumption now decides the control's sign. The bid and ask snapshots ([bid-ask-snapshots.md](bid-ask-snapshots.md)) replace it with a measurement after about 60 trading days. Until then no structure is promoted. The alternative structures proposed in the review (no stop, 250-point wings, weekly condor held to expiry) are the next thing to register, with fewer trades and so less cost drag.
