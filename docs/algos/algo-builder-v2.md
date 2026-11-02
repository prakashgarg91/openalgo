# Algo builder, next version: registration first (started 2 November 2026)

The Algos page already has a "Build your own" tab (`services/algos/builder.py`): a walk-forward search over option spreads that reports how many settings it tried and how many lost on the test period. It has four weaknesses that came out of the research: its trials never reach [TRIAL_REGISTER.md](TRIAL_REGISTER.md), re-searching reuses the same test quarter, it prices options with a model that flatters sellers, and one holdout can print "edge shown" and save straight into Sandbox. The new version puts the research discipline in the product. The design follows a review by Opus 5.5 on 2 November 2026.

## Built in this first slice

- **`services/algos/registry.py`** (files only, no database, no migration): an idea is written down in full before anything runs. Every field is required (idea, instrument, entry, exit, size, costs, benchmark, why it might work, how it fails, data already seen, data never seen, end rule, kill rule, gates, settings). Every setting is exactly one value: a list or a range is refused, because trying several is a search and each one counts as a trial. The record is frozen with a timestamp and a SHA-256 fingerprint and gets the next trial numbers. The bar a forward result must clear is 0.025 divided by the running count. The count starts at 319 (the 311 in the register plus the 8 reserved for the December screen). One new idea a month: November and December are already used, so the next free month is January 2027. A frozen file that is edited afterwards is flagged and cannot be run. A registration can be run once, and the only outcomes are "rejected" and "eligible for a forward test": nothing says an edge is shown, and nothing promotes.
- **`/algos/api/registry`** (read the register, register an idea). There is deliberately no endpoint to run, edit, delete or promote a registration in this slice.
- **"Register an idea" tab** on the Algos page (`RegistryPanel.tsx`): the count, the bar, the next free month, the list with its status, and the form.
- Registrations are stored as JSON plus a markdown copy under `db/algo_registry/` (git-ignored; copy a registration into `docs/algos/` when it should be kept in the repository).
- Tests: `test/test_algos_registry.py`, `test/test_algos_registry_api.py`, `RegistryPanel.test.tsx`.

## Built in the second slice (2 November 2026, afternoon)

- **`services/algos/eod_screen.py`**: the rejection-screen engine for the eight registered structures ([eight-structure-screen-registration.md](eight-structure-screen-registration.md)). It holds the structure definitions, the replay on end-of-day closes and settlement prices, the leg-by-leg costs (tested to add up to `costs.realistic_cost`), the six survival gates, the choice of at most two survivors (smallest drawdown first; the long straddle control never goes forward and a control that passes is flagged as a data or cost fault) and verdicts that are only "rejected" or "eligible for a forward test". Tested on made-up prices only (12 tests); no real price was evaluated.
- **`scripts/algo_backtest/eight_structure_screen.py`**: refuses before 1 December 2026 and refuses a second run, both checked before any data is read. `--check` counts coverage and evaluates no price: on 2 November 2026 it found, for the primary period (1 April 2021 to 26 September 2024), 185 weekly and 42 monthly expiries, all with a documented lot; for the overlap period (3 October 2024 to 27 October 2026) 114 weekly and 25 monthly; 161 earlier expiries are excluded because no circular-based lot is documented for them.
- **Trial counting**: every configuration the old "Build your own" search and the weekly re-check try is now added to the register's count (`registry.add_builder_trials`, called from `builder_run.py`; the search itself is unchanged). The count started at 319 on 2 November; earlier builder searches were never counted and cannot be recovered. Tests point the register at a temporary folder so they never touch the real count.

## Next slices (not built)

1. **Generalise the rejection screen** so a registration for a new idea (not only the eight structures) can be run once through `record_run`. Until then only the December screen exists, and nobody can mark a registration run, which is intended.
2. **Shadow ledger** generated from an eligible registration, on the pattern of `forward_weekly.py`, shown on the Research page next to the S3n and C1 ledgers, with the kill rule applied.
3. **Sandbox and Live gates.** Opus advised that the go-Live gate should be a forward-test pass, not "10 sandbox trades with a positive net". That gate guards real money, so it is the owner's decision and has not been touched. The builder page never goes Live.
4. Replace the old family checkboxes in `BuilderPanel.tsx` with the four steps (Write, Register, Screen, Forward) once the screen is general; the old search keeps working and is now counted.

## What the builder must never do

Edit a registration after it exists (a change is a new idea and a new trial), run a screen twice, re-search a holdout automatically, run a grid it has not counted, promote anything from a replay, or go Live.

## Ideas from the same review (nothing registered)

Ranked by honest chance of surviving; the next free idea month is January 2027, and the eight-structure screen in December already covers the option structures.

1. Volatility-scaled equity plus gold: month-end NIFTYBEES weight set by target volatility over forecast volatility (India VIX and the 20-day range, the one model the research verified), capped at one, the rest in gold and cash. Needs data already held. Most likely failure: volatility-managed portfolios seldom beat a hold of the same exposure after costs. One trial, forward shadow ledger on `etf_ledger.py`.
2. Long-only cross-sectional momentum on the 20 heavyweights (top 5 by 12-month return skipping the latest month). The list is today's, so the history is survivorship-biased and can only reject; a Nifty momentum index fund is the benchmark.
3. Variance-premium harvesting on options: already inside the December screen, add nothing.
4. Refused: pairs or basket statistical arbitrage (needs stock futures; one lot's notional and margin exceed a Rs 1 lakh account and the Rs 20,000 loss limit), expiry-week or seasonal effects and short-term residual reversal (costs consumed C1's calendar effect: 0.2 percent a year against 1.2 percent for a matched hold).

The learning pages (Open Varsity, openalgo.in/learn, 13 courses, 407 chapters) teach the same methods the registry enforces: walk-forward and purged validation, deflated Sharpe, realistic costs and impact cost, kill switches. They name pairs, cross-sectional momentum, seasonality and the variance risk premium as families; none of them offers a track record.
