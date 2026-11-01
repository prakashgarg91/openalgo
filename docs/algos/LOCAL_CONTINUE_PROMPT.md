# Prompt to continue on the local computer

Paste everything below the line into Claude Code opened in the local OpenAlgo folder (Windows PC). Written 1 November 2026.

---

Continue my OpenAlgo research from a cloud session. First read CLAUDE.md, then docs/algos/SESSION_MEMORY.md (standing rules, where things are, current state). Standing rules apply: always `uv`; no emojis; sandbox mode and analyzer mode only, never "paper trading"; never use the word "arm"; place NO live order; never print, log or commit a secret (report only "set" or "not set"); messages written for a trader; lint and format only touched files; Conventional Commits; never stage frontend/dist; no pull request unless I ask; stop and tell me if a step fails and never mock a result.

What changed in the cloud session (all on main, last commit about a80c107):
- A forward shadow test of the weekly Nifty call spread is registered (docs/algos/forward-s3n-registration.md): L1 = sell the at-the-money call and buy the call 100 points above (S3n), L2 = the same with 250 points (reference only). Entry 10:15 two sessions before the weekly expiry session, held to 15:29 of expiry day, filters VIX below 20 and no 1 percent gap down, one lot (65). First counted week: entry Fri 6 Nov 2026, expiry Tue 10 Nov. Ends at 26 completed trades or 31 May 2027. Stop at cumulative realistic net of -Rs 20,000.
- The one-minute ledger runner is built and tested: services/algos/forward_weekly.py and scripts/algo_backtest/run_forward_s3n.py (report in db/forward_s3n/report.json). It is in scripts/algo_backtest/windows/capture_option_candles.cmd after the capture. The older A/B/C forward ledger was removed from that job at my request.
- Evening Telegram alerts: scripts/algo_backtest/alert_forward.py (failed capture, missed day, week not counted, entered, closed, stop). It needs the OpenAlgo Telegram bot on.
- Sandbox bot: scripts/algo_backtest/sandbox_bot.py entry|check|exit|compare (docs/algos/sandbox-bot.md). It places the two legs through the OpenAlgo API only while analyzer mode is on, hedge first, one lot, and compares its fills with the ledger. It has been tested on a fake API only.
- The plan toward real money (from an independent review): no real money before the forward test ends; then a live registration, a static-IP VPS, tax and CA, measured slippage, kill switch.

Do these now, in this order, and report each result:
1. `git pull` on main. Run the new tests: `uv run pytest test/test_forward_weekly.py test/test_forward_alerts.py test/test_sandbox_bot.py test/test_condor.py test/test_forward_shadow.py -q`. Report pass or fail.
2. Check UPSTOX_ANALYTICS_TOKEN and OPENALGO_API_KEY are set (report only "set" or "not set"). If the first is missing, tell me how to `setx` it and stop.
3. Run `uv run python scripts\algo_backtest\run_forward_s3n.py` against my real Historify database. Show its printed output. Expect "0 completed" until the 10 Nov expiry; the point is that it reads the stored one-minute candles without error. If it errors, diagnose from log\errors.jsonl, fix the code (smallest change, with a test), and tell me.
4. Run `uv run python scripts\algo_backtest\alert_forward.py 0` and show the output. Tell me if the OpenAlgo Telegram bot is off (then alerts only reach log\capture.log) and how to turn it on and enable my notifications.
5. Confirm the nightly job: open scripts\algo_backtest\windows\capture_option_candles.cmd, check it runs capture, run_forward_s3n.py and alert_forward.py (with the capture exit code) and snapshot_historify.py in that order; check the scheduled task (install_capture_task.cmd) exists and is set for 16:00 IST on weekdays and that the PC will be on and signed in. Report what you find; do not change my schedule without asking.
6. With OpenAlgo running, logged in to Upstox (I will give the OTP and PIN when asked, used once and never saved) and switched to analyzer mode: run `uv run python scripts\algo_backtest\sandbox_bot.py entry --dry-run`. Show what it prints. It should refuse if analyzer mode is off, and otherwise print the planned symbols, quantity 65 and limit prices, placing nothing. If any API field differs from what the bot expects (quotes bid/ask/prev_close, orderstatus, openposition, expiry, holidays), fix the bot with a test and tell me. Do NOT run a non-dry `entry` unless I say so, and only on Fri 6 Nov at about 10:15.
7. Start the bid/ask snapshots: follow docs/algos/bid-ask-snapshots.md and scripts\algo_backtest\windows (download_research_data.cmd, snapshot_bidask.cmd 1015 during market hours, install_bidask_tasks.cmd). Tell me exactly what to run and confirm a snapshot file appears. Measured slippage replaces the assumed 0.15 points only after about 60 sessions and only as a registered scenario.
8. Cost check: ask me for one Upstox contract note or the brokerage calculator result for a one-lot Nifty option spread, and compare it with services/algos/costs.py (Rs 20 per order, STT 0.15 percent from 1 April 2026 on the sell side, GST, stamp duty, exchange charges, 0.15 point slippage). Report differences; do not change the registered cost model without telling me, because it would restart the count under a new version.
9. Update docs/algos/SESSION_MEMORY.md and docs/CHANGELOG.md with what ran and the results (pull first; no merge markers; no secrets), commit and push to main.

Do not: place any live order; change the registered rules, width, entry time or filters; run the sandbox bot's non-dry entry before 6 Nov; skip or shorten the forward test; add lots.

Finish with a plain-language summary: what ran, the numbers, what is still unknown, and exactly what I should do next (including keeping the PC on and signed in at 16:00 on Fri 6 Nov and Tue 10 Nov).
