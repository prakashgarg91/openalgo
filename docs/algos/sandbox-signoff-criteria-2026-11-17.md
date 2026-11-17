# Sign-off criteria for the ATM 200-wide Sandbox executor (Fable 5.2, 17 November 2026)

What the director needs from the scheduled Sandbox runs (tomorrow, Wednesday 18 November, and onward) before the live-executor build continues past its first step, and before a manual pilot start is signed off. Risking money stays the owner's decision.

## A clean cycle (entry day plus exit day) needs all of these

- **Entry:** between 10:15 and 10:20, or a logged skip with its reason.
- **Checks:** every 5 minutes from 09:20 to 15:25 on both days. At most one missed check a day, never two in a row, and none between 14:55 and 15:05 on the exit day.
- **Alerts:** zero "needs attention" or mismatch alerts.
- **Credit basis:** thresholds computed on `entry_ltp_credit`, shown in the state.
- **Slippage:** fill credit against LTP credit recorded each cycle. Flag any cycle more than 6 points short or a median above 3. These are starting thresholds for review, not fail lines.
- **Signal log:** same enter or skip decision and same strikes. Any difference in exit reason is explained in writing.
- **Hand check:** net-of-charges within Rs 5 of a hand calculation.
- **Book:** flat after exit, with exactly one trade row.

## Gates

- **Live-executor build past step one:** the Wednesday and Thursday cycle is clean.
- **Manual pilot sign-off:** four clean cycles with none unclean (positions overlap, so about one cycle per two sessions). Also: pilot limits restated against real cash, and the static IP proven by one accepted order.

## What each failure triggers

- Mismatch or unresolved alert: the build stops until the cause is found and a test added.
- Check-gap breach: fix the scheduler; the cycle does not count.
- Wrong strike, basis or exit: the clean count resets to zero.
- Hand-check mismatch: fix the ledger; the count resets.

## Telegram alerts (every message labelled Sandbox)

- Entry: strikes, expiry, quantity, LTP credit, fill credit, VIX value and its date, exit session.
- Skip: the reason.
- Exit: reason, value, gross, net, cumulative net, late flag.
- 15:30 summary: checks run against expected, and the state.
- Alert: what to look at.
