# Prompt to continue on the local computer

Paste everything below the line into Claude Code opened in the local OpenAlgo folder.

---

Continue my OpenAlgo research from a cloud session. First read CLAUDE.md, then docs/algos/SESSION_MEMORY.md (standing rules, where things are, current state, gotchas), then docs/INDEX.md. Follow them exactly: always use uv, no emojis, messages written for a trader, say "sandbox mode" and "analyzer mode", never use the word "arm", place no order, never print, log or commit a secret (report only "set" or "not set"), lint and format only the files you touch, run the tests you touch, Conventional Commits, never stage frontend/dist, no pull request unless I ask. Research discipline: pre-register rules before looking at results, report trial counts and how many lost in the untouched period, report what failed, never mock results, stop and tell me if a step fails.

Setup (do first, in this order):
1. `git pull` the openalgo repo on main.
2. Clone or pull the private data repository next to it: `git clone https://github.com/prakashgarg91/openalgo-data ../openalgo-data` (sign in to GitHub if asked). It holds bars5m (expired weekly Nifty option candles, one archive per expiry), MANIFEST.csv (an expiry listed there is complete), context/ (foreign, sector and stock daily history, plus hourly and 5-minute), index/nifty_1m.csv (Nifty 1-minute) and research/ (study tables). Never publish this data.
3. Check that UPSTOX_ANALYTICS_TOKEN is set (report only "set" or "not set"). Downloads use it; the daily broker login is only for the OpenAlgo app.

State when I left the cloud session (31 October 2026, about 02:35 UTC): the option download was at about 61 of 109 expiries and still running in the cloud. Do not run a second download at the same time: first check the manifest and `git log` in the data repository; if new expiries are still arriving, wait, or tell me so I can stop the cloud one. To finish the download here, run scripts/algo_backtest/windows/download_research_data.cmd (or `uv run python scripts/algo_backtest/fetch_upstox_expired_all.py ../openalgo-data 2024-10-01 2026-12-31 --sleep 1.0`). It resumes from the manifest and pushes each expiry. Stay under Upstox's limit of 2,000 requests per 30 minutes (about 0.7 requests a second).

Work to do once all 109 expiries are in MANIFEST.csv, in this order:
1. Run the registered regime-gated spread test ONCE: `uv run python scripts/algo_backtest/regime_spread_study.py ../openalgo-data` (use --check first, which only reports coverage). Rules are in docs/algos/regime-spread-registration.md: twelve cells, selection on the first two thirds, the last third judged once. Do not run cells before the manifest is complete. Write the results to docs/algos/regime-spread-results.md with every trial counted, how many cells lost money in the held-out third, and what failed.
2. Extend the Nifty 1-minute file back: `uv run python scripts/algo_backtest/fetch_index_1m.py ../openalgo-data 2022-01-03`, then run the registered intraday momentum test ONCE (`scripts/algo_backtest/intraday_momentum_study.py`, rules in docs/algos/intraday-momentum-registration.md), and write docs/algos/intraday-momentum-results.md.
3. Add both results to the Research page: extend scripts/algo_backtest/export_linkage_graph.py and the page in frontend/src/pages/Research.tsx, rerun the exporter, build the frontend to check it (`cd frontend && npm run build`), then restore dist with `git checkout -- frontend/dist` and never stage it.
4. Update docs/algos/SESSION_MEMORY.md (state, numbers, next step) and docs/CHANGELOG.md, commit and push to main.

What has been found so far (details in docs/algos/*-results.md): the US close explains the Nifty's opening gap but nothing after the open held up in 2017 to 2026; foreign moves shift sector and stock opening gaps but the second step to the Nifty is almost absent; nothing predicts direction a week or a month ahead and a three-number volatility baseline (India VIX, own 20-day volatility, 20-day return) beats a 288-input model; India VIX has paid more than it delivered, with fat tails, and selling only when it looks rich did not help; the day's range is ranked well by India VIX and yesterday's range. So an edge, if any, must come from the trade's structure, which the option replay tests.

Finish with a plain-language summary: what ran, the numbers, what is still unknown, and exactly what I should do next.
