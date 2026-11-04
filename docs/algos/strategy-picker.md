# Strategy picker (4 November 2026)

The Strategy picker tab on the Algos page lists 24 option structures priced from the live Nifty chain. For each one it shows what it can earn and lose for one lot held to expiry, the capital it needs, the entry credit or debit, the breakevens, the round-trip costs, a fit score and what has actually been tested. The trader chooses. It never names a pick, places an order, registers an idea or promotes anything to Live.

## What each column means

- **Most it can earn / lose**: payoff at expiry from the mid prices of the live quotes. "Unlimited" is shown as such.
- **Capital needed**: the broker's own margin for the basket (Upstox margin calculator) when it answered within 25 seconds; otherwise the premium paid, or the worst loss for a credit structure, labelled as an estimate.
- **Costs, in and out**: brokerage, STT, exchange, SEBI, GST and stamp from the realistic cost model, plus the full bid-ask spread of each leg for getting in and out once.
- **Fit**: 0 to 100, how well today's conditions match the structure's design. Weights: direction 25 percent (the regime's bias and the move since the open), volatility 20 (India VIX level and change against buying or selling premium), size against the daily loss cap 20, liquidity 15 (costs against premium), time of day 10, days to expiry 10. It is **not a forecast of profit**; the trend and volatility readings are heuristics, not tested rules.
- **Evidence**: only three structures have anything behind them (the bear call spread is the S3n forward test, running in Sandbox; the iron condor and iron fly were replayed on 108 expiries with no edge after costs). Everything else says "Untested".

## Limits

A structure is listed under "Outside your limits", with the reason, when its loss is unlimited, its worst loss is above the daily cap (`ALGO_MAX_DAILY_LOSS_INR`, default Rs 20,000), it needs more than the capital (`ALGO_CAPITAL_INR`, default Rs 1,00,000), or a strike has no two-sided quote.

## Code

`services/algos/picker.py` (pure scoring and payoff), `services/algos/picker_inputs.py` (chain, market reading and margins), `GET /algos/api/picker`, `frontend/src/components/algos/PickerPanel.tsx`. Tests: `test/test_algos_picker.py`, `test/test_algos_picker_inputs.py`.

## Not done

Calendar and diagonal structures (two expiries) and the 8-leg double condor and double fly are not in the list. The picker does not yet use volume or open interest in the score beyond the quote spread. The live endpoint has not been exercised against the broker from this build: the first run is the trader's, and the tests use made-up chains.
