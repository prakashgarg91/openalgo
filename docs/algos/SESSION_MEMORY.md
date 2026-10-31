# Session memory (read this first, update it before a work block ends)

Plain notes that carry context between Claude sessions. No secrets, ever: report a secret only as "set" or "not set". Keep each section short and current; move old items to the log at the bottom.

## Standing rules from the trader

- Sandbox (analyzer) mode only. Place no order. Switch the app to analyzer mode after every broker login (Live is the default after login).
- Pre-register rules and pass numbers before looking at results; report trial counts and how many lost in the untouched last third; report what failed.
- Never mock results. If a step fails, stop and say so.
- Push to the session branch, then `git push origin HEAD:main` and `git push origin HEAD:ccr-efb53d25-92612q`. No pull request unless asked.
- Lint and format only the files touched. Conventional Commits. Never stage `frontend/dist`. No emojis. Say "sandbox mode" / "analyzer mode", never "paper trading"; never the word "arm".

## Where things are

- Code, docs, results: `prakashgarg91/openalgo` (this repo). Option candles: private repo `prakashgarg91/openalgo-data` (see [research-data.md](research-data.md)). Never publish the data. Not Google Drive or Sheets.
- In a cloud session the data repo is attached with `add_repo` and cloned to `/home/user/openalgo-data`. The trader's local computer clones it and runs `git pull`.
- Nightly capture of live contracts (Windows task, trader's machine): [option-capture.md](option-capture.md).
- Shadow tests registered in advance: [forward-test-registration.md](forward-test-registration.md).

## Daily routine

1. Ask the trader for the Upstox login (mobile number, then OTP, then PIN). It expires about 3:30 AM IST. A browser step (Playwright for Node, `NODE_PATH=$(npm root -g)`) waits for the OTP and PIN; use them once, never save or commit them.
2. Switch to analyzer mode, then continue.
3. Downloads use the long-lived read-only `UPSTOX_ANALYTICS_TOKEN` (set as an environment secret), not the daily login.

## Current state (update this section)

- Option data pull: `uv run --no-sync python scripts/algo_backtest/fetch_upstox_expired_all.py /home/user/openalgo-data 2024-10-01 2026-10-31 --sleep 1.0 >> log/data_pull.log`. Resumes from `MANIFEST.csv`. 109 expiries (3 Oct 2024 to 27 Oct 2026), 7,907 requests, about 3.5 hours at 1.0 s. Upstox limit is 2,000 requests per 30 minutes; stay under it.
- Context data (done 2026-10-31): `openalgo-data/context/{daily,hourly,min5}/<symbol>.csv` and `context/MANIFEST.csv` from `scripts/algo_backtest/fetch_context_data.py` (Yahoo, no login). 110 series: US and global risk, US futures, FX, commodities, Asia, Europe, India sector indices, 20 Nifty heavyweights; daily since 1970 to 2007 depending on series (Nifty 2007, India VIX 2008), hourly about 2 years and 5-minute about 60 days for 18 key series (5-minute is a rolling snapshot: refresh it, or it is lost). TATAMOTORS.NS returned nothing (symbol changed after the demerger; use the new ticker). Timestamps are UTC.
- Linkage study done once (31 Oct 2026): [linkage-study-results.md](linkage-study-results.md). US close predicts the Nifty gap (OOS R2 0.24) but intraday links reversed and none verified; range is explained by India VIX level and previous range, foreign data adds 0.03. Tables in `openalgo-data/research/linkage/`. Next candidates: domino chains (new registration), intraday follow-through with the 60-day 5-minute snapshot, using VIX and range for stop width.
- One-click Windows launcher: `scripts/algo_backtest/windows/download_research_data.cmd` (pulls the data repo, refreshes context data, resumes the option pull). A button inside the app does not exist yet.
- Range model done (docs/algos/range-model-results.md): baseline (India VIX of D-1, range of D-1) stays; its 5 groups rank days well (top group 3.6x the bottom range).
- NEXT STEP when all 109 expiries are in MANIFEST.csv: run ONCE `uv run --no-sync python scripts/algo_backtest/regime_spread_study.py /home/user/openalgo-data` (registration: docs/algos/regime-spread-registration.md; selection on the first two thirds, then the held-out third). `--check` only reports coverage. Do not run cells before the pull is complete. Index file `openalgo-data/index/nifty_1m.csv` (Nifty 1-minute, 20 Sep 2024 to 30 Oct 2026) was downloaded by `fetch_index_1m.py`; refresh if more days are needed.
- Research page built (`/research`): `blueprints/research.py`, `frontend/src/pages/Research.tsx`, `frontend/src/components/research/LinkageMap.tsx`, data `docs/algos/research/linkage.json` from `scripts/algo_backtest/export_linkage_graph.py <data_repo>` (re-run it after any new study result). Verified in a browser (dark theme, mobile, no console errors). `frontend/dist` is rebuilt locally and never staged; CI builds it on main.
- Domino chain test done (docs/algos/domino-chain-results.md): foreign to sector/stock opening gaps is real (152 of 491 verified), but the second step to the Nifty after the open is almost absent (4 of 58); nothing usable. India VIX open in the Yahoo data is stale (90% equal to previous close): the VIX open is untested; CNXFIN and CNXMEDIA have one row each.
- Literature notes + variance risk premium test done (docs/algos/literature-notes.md, vrp-results.md): premium positive in both halves (VIX above realised on 78% of days, +3.7 vol points) but fat-tailed; expected-premium gate FAILED (q5 minus q1 payoff -45, t -0.23). Remaining candidates: the range-group gate on option data; intraday momentum on Nifty 1-minute bars (not yet registered).
- Research page now has a Chains tab. After any new study, rerun `scripts/algo_backtest/export_linkage_graph.py <data_repo>` and rebuild.
- Multi-horizon study done (docs/algos/horizon-study-results.md): no direction predictor at 5 or 20 days (3 selected, 0 verified; joint R2 about 0); volatility is predictable (165 of 180 verified for 5-day) but the 3-input baseline (India VIX, own 20-day vol, 20-day return) beats the 288-input model (R2 0.553 vs 0.488). Conclusion across all studies: no market predicts Nifty direction after the open; keep VIX + range as the volatility input.
- STATE AT END OF 31 Oct 2026: every registered test is run. Option data complete (108 of 109 expiries). Findings: no foreign signal, chain, horizon or intraday-momentum link predicts Nifty direction in 2017-2026; volatility is predictable from India VIX + recent range; the VIX premium is real but fat-tailed; every Zen-style spread cell loses money after conservative costs (about Rs 270 a trade), with or without the range gate. The open question that could change this: the conservative cost model (pre-cost control +68k vs costs 90k) and other structures (wider/narrower, no stop, other entry times, defined-risk strangles, hold to expiry). Next step if continuing: register a cost-model check (real brokerage/STT/slippage) and a small set of alternative structures BEFORE running them; and the forward shadow test (252 sessions) via the nightly capture. Cloud checks are stopped.
- Goal in force: check status every 15 minutes (send_later chain), keep the option pull alive, finish analysis and building.
- Zen result so far: exits reproduce, no side rule has an edge in the last third (34 of 36 cells lost). Catalogue Zen unchanged.
- Plan agreed with the trader: find cross-market and sector links on the long daily history first (15+ years), keep only links with a written reason that were known before 10:15 India time, then translate survivors to spread outcomes on the option data, with the last third untouched and every trial counted. News and sentiment are deferred. NSE's site blocks the cloud session (403), so FII and DII flows need another route.
- Next: when the pull is complete, write the pre-registered test plan for a regime-aware rule set (choose on the early part, hold back the last third), then run it once.

## Gotchas that cost time

- `uv run` re-syncs and removes gunicorn: install gunicorn and eventlet, then launch with `uv run --no-sync`.
- Under no terminal the dev server refuses to start; use `gunicorn --worker-class eventlet -w 1`.
- `.env` overrides environment variables (`override=True`); a placeholder there wins over a real secret in the environment. `.env` is git-ignored.
- `pkill -f` can match its own shell; put the pattern in brackets (`[g]unicorn`) and run it in its own command.
- The cloud container is reclaimed when idle and the app stops between turns; anything not pushed is lost.
- OpenAlgo is single user: there is one owner account, no second login.

## Log

- 2026-10-31: attached `openalgo-data`, started the 109-expiry pull, added this file.
- 2026-10-31: pushed 110 context series to the data repo.
- 2026-10-31: linkage study run and recorded; one-click download launcher added.
- 2026-10-31: Research page added.
- 2026-10-31: domino chain test run and recorded.
- 2026-10-31: literature notes, VRP test, chains tab.
- 2026-10-31: multi-horizon study run and recorded.
- 2026-10-31: Research page now also has Horizons and Premium tabs (rerun export_linkage_graph.py after new studies).
- 2026-10-31 (cloud): the cloud option pull died once because the data repo moved (the trader's local session pushed the extended Nifty 1-minute file and the intraday momentum table). Fix: `git -C /home/user/openalgo-data pull --rebase origin main`, then restart the fetch. Both machines push to the data repo, so always pull --rebase before restarting. The intraday momentum test is done (0 of 12 verified, docs/algos/intraday-momentum-results.md): do not rerun. Regime-gated spread test DONE (docs/algos/regime-spread-results.md): 108 of 109 expiries (2024-12-26 unavailable at Upstox); all 12 cells lose in selection and held out; none selected. A replay defect (5-minute bars end 15:25, code expected 15:29, so expiry-day positions stayed open for ever) was fixed with a `last_bar` argument and disclosed; the held-out third was replayed twice. The Research page has an Option tests tab with both results.
- 2026-10-31: option pull complete (108 of 109 expiries, one unavailable); regime-gated spread test run: no cell qualifies.
- 2026-10-31 (late): cost scenario registered and applied (docs/algos/cost-scenario-results.md): realistic cost about Rs 155 a trade vs about Rs 270; all 12 cells still do not qualify; the always-sell-calls control is +Rs 17k selection / +Rs 7.6k held-out but negative at twice the costs and drawdown 36-57k vs the Rs 20k limit; rules A and B lose even before costs. Bid and ask snapshots built (services/bidask_snapshot.py, scripts/algo_backtest/snapshot_bidask.py, summarize_bidask.py, Windows tasks install_bidask_tasks.cmd, docs/algos/bid-ask-snapshots.md): NOT yet running (needs the trader's Windows PC, token and the data repo). After about 60 days replace the 0.15-point slippage with the measured half-spread, register that as a third scenario first. Next to register: the alternative structures S1-S4 from the Opus review (250-point wings, no stop, weekly condor to expiry).
