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

## Research data and past weeks (added the same day)

- **Research data.** The picker reads `docs/algos/research/linkage.json`. Its study found, on years it had not seen when it chose its links, that overseas markets predict the Nifty's opening gap (R squared 0.24) and that nothing it tried predicts the move after the open (R squared below zero). So before the open, and in the first five minutes, the direction score uses a rough expected gap (the average of each verified link's estimate: S&P 500, Nasdaq and the dollar index). After the open direction is allowed only a small tilt (35 percent of its usual spread), and volatility, cost and your limits do most of the work. The page shows the expected gap, the markets behind it and the study's own verdict.
- **Past weeks.** `scripts/algo_backtest/picker_history.py <data_repo>` replays every structure the end-of-day engine can price (up to four legs, so the 8-leg ones are not included) on the NSE end-of-day files: entered two sessions before a weekly expiry, held to expiry, after realistic costs, one lot. It writes `db/picker_history/history.json` (git-ignored; 251 weeks from April 2021 to October 2026 on the first run). The picker shows the average, win rate, worst week, the older and recent thirds, and the figures for weeks with India VIX in the same band as today (low under 14, mid 14 to 18, high 18 to 20), only when there are at least 15 such weeks. Weeks entered above India VIX 20 are not in the replay, so there is nothing to show when VIX is above 20.
- **What this is not.** It is a description, not a trial and not a selection: nothing is registered, ranked by past profit or counted. It is held-to-expiry weekly results, not a 15-minute trade. Structures with unlimited loss show a worst week that is not a limit.
- **Speed.** The picker no longer fetches broker margins by default (24 calls were slowing the whole app). Press "Get broker margins" and it fetches them only for the structures inside your limits, within 12 seconds. Results are cached for 45 seconds, errors are not cached, and the page no longer refreshes by itself.

## Scenarios, filters and tracked picks (4 November 2026, evening)

- **If Nifty ends here at expiry.** Each row shows its result after costs if Nifty ends at expiry two or one typical moves down, flat, or one or two up. One typical move is India VIX scaled to the days left (`services/algos/picker_scenarios.py`). A what-if, not a forecast. Hidden when India VIX is unknown.
- **Filters and sort** (in the page): defined risk only, most it can lose up to, capital needed up to, costs up to, and six sort orders. They apply to the "Within your limits" table only.
- **Tracked picks and the My picks tab.** The Track button on a row records the structure's legs, entry mid prices, fit score and the day's conditions in `db/pick_log/picks.jsonl` (git-ignored). **No order is placed.** My picks follows each open pick with live mid prices and closes it at the live result or at a result the trader types in. After 10 closed picks it shows the rank correlation between fit score and result, and after 20 a one-line verdict on whether the fit score meant anything. That is the evidence the picker cannot give by itself. Endpoints: `GET/POST /algos/api/picks`, `POST /algos/api/picks/<id>/close`. Code: `services/algos/pick_log.py`.
- **Built by:** Haiku workers wrote the scenario calculator, the pick log and the page parts under Sonnet's review and tests.
