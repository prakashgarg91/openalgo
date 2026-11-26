# Go or no-go file: ATM 200-wide call credit spread (DRAFT, started 26 Nov 2026; final due about 19 Dec 2026)

GPT-6-Astra's week-4 file (docs/algos/astra-review-2026-11-23.md). Filled as evidence arrives. The decision is the
owner's; this file states the evidence and a recommendation.

## 1. Capital and limits (owner, 25 Nov)
- Real cash Rs 32,041; funding of about Rs 26,000 only after a go.
- Pilot limits: daily loss budget Rs 5,000, pause at Rs 10,000, max 3 entries a week, skip any trade whose largest
  loss does not fit. Budget rises to Rs 10,000 for one lot only after 10 closed counted Sandbox trades net positive
  after charges, no machinery failure, and a go.
- One lot's largest loss: (200 - credit) x 65, about Rs 6,500 to 9,100.

## 2. Past-data evidence (all on data already looked at; about 361 trials so far)
- Replay, lot by expiry: 388 trades, net Rs 1,71,325 realistic, t 2.47, deepest fall Rs 43,723.
- At one lot of 65: net Rs 1,82,171, t 2.72, deepest fall Rs 38,032.
- Timing stress, combined: net Rs 1,16,092 (lot by expiry), t 1.59; the stop checked inside each bar is what hurts.
- Filters: the 21 gate-skipped days lost; gated beats ungated (weak, 21 trades).
- Weekly premium exceeded the following move on 64 percent of days, mostly in the nervous half of VIX.
- Costs match official rates; lot table fixed (January 2025); 20 trades hand-checked.
- 100-wide version retired by its own stop sign (trial 360).

## 3. Sandbox evidence (to be completed)
| Trade | Entry | Exit | Reason | Net after charges |
| --- | --- | --- | --- | --- |
| 1 | 18 Nov | 19 Nov 15:00 | time | Rs -2,954 |
| 2 | 25 Nov | (26 Nov) | | |

Machinery: first cycle end to end clean; failure drills passed on a separate test bot (25 Nov). Missed days:
20 Nov (PC off), 24 Nov (holiday, correct), 23 Nov (expiry day, correct skip).

## 4. Execution
Sandbox fills within about Rs 42 of screen prices on trade 1. Untested live: partial fills, a refused hedge, a stale quote.

## 5. Recommendation (to be written on the due date)
Fixed now so it is not shaped by the result: GO for a one-lot manual pilot only if all hold on the due date:
(a) no machinery failure in the counted Sandbox trades; (b) the owner's 10-trade condition is met, or the owner
chooses to start under the Rs 5,000 budget (in which case no trade fits and the pilot simply waits);
(c) funding is in place. Otherwise NO-GO for now, Sandbox continues.
