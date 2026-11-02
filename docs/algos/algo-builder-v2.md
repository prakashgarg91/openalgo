# Algo builder, next version: registration first (started 2 November 2026)

The Algos page already has a "Build your own" tab (`services/algos/builder.py`): a walk-forward search over option spreads that reports how many settings it tried and how many lost on the test period. It has four weaknesses that came out of the research: its trials never reach [TRIAL_REGISTER.md](TRIAL_REGISTER.md), re-searching reuses the same test quarter, it prices options with a model that flatters sellers, and one holdout can print "edge shown" and save straight into Sandbox. The new version puts the research discipline in the product. The design follows a review by Opus 5.5 on 2 November 2026.

## Built in this first slice

- **`services/algos/registry.py`** (files only, no database, no migration): an idea is written down in full before anything runs. Every field is required (idea, instrument, entry, exit, size, costs, benchmark, why it might work, how it fails, data already seen, data never seen, end rule, kill rule, gates, settings). Every setting is exactly one value: a list or a range is refused, because trying several is a search and each one counts as a trial. The record is frozen with a timestamp and a SHA-256 fingerprint and gets the next trial numbers. The bar a forward result must clear is 0.025 divided by the running count. The count starts at 319 (the 311 in the register plus the 8 reserved for the December screen). One new idea a month: November and December are already used, so the next free month is January 2027. A frozen file that is edited afterwards is flagged and cannot be run. A registration can be run once, and the only outcomes are "rejected" and "eligible for a forward test": nothing says an edge is shown, and nothing promotes.
- **`/algos/api/registry`** (read the register, register an idea). There is deliberately no endpoint to run, edit, delete or promote a registration in this slice.
- **"Register an idea" tab** on the Algos page (`RegistryPanel.tsx`): the count, the bar, the next free month, the list with its status, and the form.
- Registrations are stored as JSON plus a markdown copy under `db/algo_registry/` (git-ignored; copy a registration into `docs/algos/` when it should be kept in the repository).
- Tests: `test/test_algos_registry.py`, `test/test_algos_registry_api.py`, `RegistryPanel.test.tsx`.

## Next slices (not built)

1. **Rejection screen** that reads a registration and runs it once on the NSE end-of-day data (`nse_eod.py`, `nse_lots.py`, `costs.py`), reporting how many configurations lost, the doubled-cost result and the halves; it writes its gate results through `record_run`. Until it exists nobody can mark a registration run, which is intended.
2. **Shadow ledger** generated from an eligible registration, on the pattern of `forward_weekly.py`, shown on the Research page next to the S3n and C1 ledgers, with the kill rule applied.
3. **Sandbox step** that opens only after a forward test has ended and passed; today's "10 sandbox trades with a positive net" gate is not enough. The page never goes Live.
4. Retire or count the Sunday re-search and the "check for a better version" pass in the old builder.

## What the builder must never do

Edit a registration after it exists (a change is a new idea and a new trial), run a screen twice, re-search a holdout automatically, run a grid it has not counted, promote anything from a replay, or go Live.

## Ideas from the same review (nothing registered)

Ranked by honest chance of surviving; the next free idea month is January 2027, and the eight-structure screen in December already covers the option structures.

1. Volatility-scaled equity plus gold: month-end NIFTYBEES weight set by target volatility over forecast volatility (India VIX and the 20-day range, the one model the research verified), capped at one, the rest in gold and cash. Needs data already held. Most likely failure: volatility-managed portfolios seldom beat a hold of the same exposure after costs. One trial, forward shadow ledger on `etf_ledger.py`.
2. Long-only cross-sectional momentum on the 20 heavyweights (top 5 by 12-month return skipping the latest month). The list is today's, so the history is survivorship-biased and can only reject; a Nifty momentum index fund is the benchmark.
3. Variance-premium harvesting on options: already inside the December screen, add nothing.
4. Refused: pairs or basket statistical arbitrage (needs stock futures; one lot's notional and margin exceed a Rs 1 lakh account and the Rs 20,000 loss limit), expiry-week or seasonal effects and short-term residual reversal (costs consumed C1's calendar effect: 0.2 percent a year against 1.2 percent for a matched hold).

The learning pages (Open Varsity, openalgo.in/learn, 13 courses, 407 chapters) teach the same methods the registry enforces: walk-forward and purged validation, deflated Sharpe, realistic costs and impact cost, kill switches. They name pairs, cross-sectional momentum, seasonality and the variance risk premium as families; none of them offers a track record.
