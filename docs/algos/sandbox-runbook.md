# ATM 200 sandbox bot: runbook

For the trader running the bot on the PC. It places orders only in OpenAlgo's **Sandbox** (analyzer) mode, never Live. The rule and the order logic are in [sandbox-bot.md](sandbox-bot.md).

## What it does each day

- **10:16 (weekdays): entry.** The bot checks the India VIX gate and the expiry window. If both pass, it buys the bought call first (the hedge), then sells the sold call once the hedge has filled. If the day is skipped, it writes that down and does nothing more today.
- **Every 5 minutes, 09:20 to 15:25 (weekdays): check.** It confirms both legs are still held, settles any order whose reply was lost, then applies the exit rules: target, stop, or the time exit at the **15:00 check on the session after entry**. The buy-back of the sold call is always sent before the sale of the hedge.
- **Trades** go to `db\sandbox_bot_atm200\trades.csv`, one row per closed trade. The current state is `db\sandbox_bot_atm200\state.json`.

Commands (run from the repository folder with `uv run python scripts/algo_backtest/sandbox_bot_atm200.py ...`):

- `status`: prints the recorded state as JSON. Read `status`, `needs_attention` and `inflight` first.
- `flatten --yes`: reads the account, buys back a short call and sells a held hedge, both at market, and records the trade as `flattened_by_person`. It books nothing to `trades.csv`, so note its result yourself.
- `entry` and `check` run by the scheduler. Add `--dry-run` to see what they would do without placing anything.

## What each state means

| State | Meaning | Do you act? | What to do |
| --- | --- | --- | --- |
| `flat` (no status) | Nothing recorded yet. | No. | None. |
| `entering` | The bot stopped in the middle of the entry, so it is not known what was sent. | Yes. | Look at the positions in OpenAlgo. Then run `flatten --yes` if anything is held. |
| `not_placed` | The first order was refused, so nothing was held. | No. | None. The day is used up. |
| `no_hedge` | The bought call did not fill within 60 seconds and was cancelled. Nothing is open. | No. | Confirm the order is cancelled in the order book. |
| `orphan_hedge` | The bought call is held and the sold call is not (not placed, or only partly filled). | Yes. | Look at the positions. Run `flatten --yes` to sell the hedge. |
| `open` | The spread is held and being checked. | No. | Nothing. Exits happen on their own. |
| `short_bought_back` | The sold call is closed, the hedge still needs selling. | Only if a flag shows. | Normally the next check sells the hedge. If `needs_attention` is set, look, then `flatten --yes`. |
| `closed` | The trade is finished and written to `trades.csv`. | No. | Check the row if you want. |
| `skipped` | No entry today, with the reason in `reason` (for example VIX 20 or higher). | No. | None. The next session's entry runs normally. |
| `flattened_by_person` | Closed with `flatten --yes`. Not in `trades.csv`. | No bot action. | Record its result by hand. No further orders are sent. |
| `needs_attention` (a flag, not a status) | Something is unclear, so the bot sends nothing and does not manage the trade. | Yes, now. | Read the alert. Check the positions and the order book. Then run `flatten --yes` if the legs are not what the state says. A flagged open trade is not exited by the bot, so do not leave it. |

## Specific situations

- **The PC was off at 10:16.** No entry happens that day. Do not start `entry` later on the same day unless you have decided to trade it; it refuses after 10:45 anyway. Missed checks are not a problem in themselves. If the exit was due while the PC was off, the next check exits the trade and the row says `late`.
- **OpenAlgo was restarted mid-trade.** Start OpenAlgo, log in to the broker, and confirm Sandbox mode is on. Run `status`. The next check reads the state from disk and settles any order that was in flight. Do not re-send anything by hand.
- **An alert arrives.** Read it. It says what it found. Look at the positions and the order book in OpenAlgo, then `status`. Do not place orders to "fix" it first. The bot sends one alert per reason, so repeats mean the state has not changed.
- **Analyze mode was switched to Live.** The bot refuses every action and says Sandbox is not on. Switch OpenAlgo back to Analyze (Sandbox) mode. Then look at the positions before the next check runs.

## Never

- Never edit `state.json` or `trades.csv` by hand. Use `status` and `flatten --yes`.
- Never run `entry` outside 10:10 to 10:45, and never use `--force`.
- Never run any bot command with OpenAlgo in Live mode.
- Never run `flatten --yes` without first reading `status` and the positions.
- Never send orders in OpenAlgo to close a bot trade without `flatten --yes`, unless the bot has been stopped and you are closing by hand on purpose.
