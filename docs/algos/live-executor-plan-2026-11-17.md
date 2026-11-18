# Live executor for the ATM 200-wide rule: build plan (draft for owner approval, 17 November 2026)

Approved by the owner on 17 Nov 2026 to START after the first scheduled Sandbox entry (18 Nov); nothing built yet; nothing may run until the owner approves the module. Roles: Fable 5.2 directs and reviews, Haiku 5.5 builds in scratch copies, Sonnet 5.5 coordinates and verifies, the owner approves and switches Live on. The Sandbox executor (`services/algos/sandbox_bot_atm200.py`) stays Sandbox only and is not changed into a live one.

## Why a separate build

The Sandbox bot refuses to run unless the app is in Analyze mode, and every order it sends carries `sandbox_only`. A live executor must do the opposite on purpose, so it is a separate module with its own tests, reviewed on its own.

## Fable's must-do list before the first real order

1. Pass `force_live` explicitly. The live path must never follow the analyzer toggle (CLAUDE.md: an order path decides once, under the lock, and never on a global switch).
2. Margin check before the hedge order, and again for any overnight (NRML) hold. Real cash is about Rs 32,041, not Rs 1,00,000.
3. Restate the limits against real cash: cap and ledger stop were set against Rs 1,00,000. Owner chose a pilot pause at cumulative Rs 10,000 loss.
4. Exit found cancelled and unfilled: stop and alert a person, never re-send.
5. A filled hedge after a lost entry reply stays flagged for a person (already so in Sandbox).
6. Order matching uses India time; either assert the machine clock is India time or convert.
7. Partial fills: cannot be tested in Sandbox. Plan: first real orders are one lot of liquid contracts, limit orders at the touch, and a person watches the first five trades.
8. Static IP: confirmed only when Upstox accepts a real order (the registered primary address 151.245.182.73 matches the proxy exit address, checked 17 November).
9. Sign-off needs clean scheduled Sandbox runs up to the pilot date (Fable's condition), not one clean trade.

## Proposed build steps (about a week, owner approves each gate)

1. Haiku: `services/algos/live_executor_atm200.py` composing the same reconcile, in-flight and flatten logic, with `force_live=True`, a hard refusal unless an owner approval file for the day exists (written by the owner, expires at 15:30), no `sandbox_only`, and the pilot limits as constants read from one place.
2. Haiku: tests with a fake client only (no real app): every case of the Sandbox bot plus margin refusal, approval-file missing or stale, mode mismatch, and the cap and pause lines.
3. Sonnet: review the diff, run the suites, break the guards on purpose to confirm the tests fail.
4. Fable: review the order path and the approval gate.
5. Owner: funds, approval file for the day, Live switch.
6. First real week: one lot, supervised, daily net-of-charges report; pause at cumulative -Rs 10,000.

## What it will not do

Run without the owner's daily approval, size above one lot, hold more than one position, change the frozen rule, or place any order while the app is in Analyze mode.

## Cost and risk

Cost: one week of Haiku and Sonnet time and Fable reviews. Risk: real money at stake only after step 5, and the pause line bounds the pilot's loss at about Rs 10,000 plus the open trade.

## Relation to the Live gate (open owner decision, written down so it is not routed around)

The Live gate (`ALGO_LIVE_REQUIRES_FORWARD_PASS`, on by default) refuses a Live algo order without a recorded forward pass and a written post-mortem; for the ATM 200-wide rule that cannot exist before about May 2027. The owner chose (17 Nov 2026) a MANUAL pilot from 1 Dec with the gate left on: the owner places each trade by hand in the app, which the gate does not cover. The live executor therefore must not quietly bypass the gate: it either honours it (and stays unused until a forward pass exists), or refuses to start unless the owner has switched the gate off in writing for this one rule, and says so loudly in its first alert. Nothing automatic runs live before that written decision.

## Owner decisions of 18 November 2026

- Margin buffer: the larger of Rs 3,000 or 10 percent of the required margin (Fable's rule), replacing the Rs 2,000 placeholder. To be implemented when the executor is merged.
- Live gate: confirmed ON with a MANUAL pilot from 1 December and NO waiver. The executor stays unused until a forward pass exists or the owner writes a waiver in the approval file later.
- gthread suite: an exception is recorded for the `live_only` order-API change until a Linux environment exists (see the changelog).
- Daily cap: the structural check (width x lot x lots must not exceed Rs 27,000) replaces any profit-and-loss tracking for the pilot; one lot and one position bound a day's loss at about Rs 13,000.
