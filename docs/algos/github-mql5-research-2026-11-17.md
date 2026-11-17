# GitHub and MQL5 research digest (17 November 2026)

Three Haiku 5.5 agents read public GitHub and MQL5 pages, read only, under Fable 5.2's brief (no code copied, no backtests, nothing registered). Evidence is thin. Nothing here is adopted: Fable reviews first, and any hypothesis goes through the one-idea-a-month register (next free slot February 2027).

## Topic A: ideas (credit spreads, volatility regimes, overnight carry)

- **mahav235-svg/nifty-options-lab (MIT):** an overnight short straddle is profitable before costs, not after; Indian statutory cost schedule worth checking against ours; walk-forward, deflated Sharpe and PBO checks are the validation pattern; its one positive candidate was picked from 359 variants (caution).
- **Finaur VIX regime write-up:** a VIX moving-average gate cut drawdown on S&P 500 buy-and-hold only; a hypothesis for a pre-fixed gate test on Nifty.
- **nifty-orb-options:** ATM short with a 200-point wing, same width as our candidate; the page returned 404, rules unverified.
- **nifty-credit-spread-paper:** a Zen replica (already rejected shape); demoted.
- **Negative reference:** a SPY and QQQ credit-spread repo found no setup that beat random entry out of sample.
- No MQL5 article covers index-option credit spreads with a VIX gate and a backtest.

## Topic B: methods (walk-forward, multiple testing, trial counting)

- **Kodezilla0725/deflated-sharpe (MIT, 144 tests):** DSR and PBO; mirror as a cross-check, not a dependency; verify its listed errata and the kurtosis convention first.
- **bashtage/arch SPA module:** Hansen SPA and White reality check; strongest test for "the selected strategy beats the field after search"; licence to confirm.
- **eslazarev/purged-cross-validation (MIT):** purged walk-forward and CPCV; reproduce its textbook example before use.
- **s9d9m/backtest:** an append-only experiment ledger pattern (we already have the register).
- Found nothing for nested validation or for strategy-selection regime switching with a 40-trade minimum.

## Topic C: execution and India

- **Lumibot PRs #1250 and #1272:** multi-leg cumulative-fill reconciliation and reopening a parent after a later partial fill; design input only; merge state and licence unchecked.
- **oh-my-tradeagent PR #896:** client-order-id idempotency; a partial fill stops re-sending.
- **jugaad-data:** F&O bhavcopy ingest with caching; it scrapes NSE, so validate checksums and schema and keep the raw archive.
- **Dated statutory-rate table (Shivaansh29/nifty_backtest):** the design of keeping rates in a table cited to circulars; the STT in a separate MIT straddle repo looks stale, so re-derive every rate from circulars.
- **upstox-python (MIT, official):** a thin order adapter only; no reconciliation logic.
- SEBI static IP: no SEBI primary text found on whether a proxy IP is acceptable; the question stays open and is the owner's to settle with Upstox.

## What it changes for us

Nothing is adopted. Candidates for Fable's review: a deflated-Sharpe and PBO cross-check for the monthly selector (engineering), an SPA test for the selector against a benchmark (engineering), the reconciliation patterns as test ideas for the live executor, and a pre-fixed VIX gate test as a possible hypothesis in the February 2027 slot.
