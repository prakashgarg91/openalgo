# What "complete" means, and where we stand (8 November 2026)

Owner's goal: a system ready for algo trading that is better than Zen from Stratzy. Two layers, because only the first can be finished by working, and the second can only be shown by waiting.

## Layer 1: the system is ready (can be finished by work)

| # | Item | State on 8 Nov | Needs |
| --- | --- | --- | --- |
| 1 | Data capture, bid-ask snapshots, ETF ledgers, S3n runner, Zen follow ledger run by themselves | Built and scheduled | PC on and signed in every trading day |
| 2 | A missed login or missed day is noticed within minutes | Built and scheduled Monday to Friday at 09:20, 10:30 and 16:30 (`scripts/algo_backtest/daily_check.py`; tasks "OpenAlgo daily check morning, midday, evening"). A Friday-holiday Monday or a market holiday will warn; that is noise | Telegram bot on for phone alerts; until then it writes `log/daily_check.log` |
| 3 | Always-on machine so days are not missed | Not done | Owner decision and a small Mumbai server |
| 4 | Static IP for order writes | Done: proxy renewed to 11 Feb 2027, tested, Readiness checks it | Renew before 11 Feb 2027 |
| 5 | Live gate: no Live order without a recorded forward pass and a written post-mortem | Built, on by default | Leave on |
| 6 | Risk limits: Rs 1,00,000 capital, Rs 20,000 daily cap, one lot, defined risk only | In the picker and the live gate | Keep |
| 7 | Cost model checked against a real Upstox contract note | Not done | One real contract note from the owner |
| 8 | Kill switch tested end to end | Not done | Market hours, sandbox mode |
| 9 | Why the two live orders were rejected | Parked as a funds issue | Upstox rejection text, or a funded account |
| 10 | Strategy picker, tracked picks, research linkage | Built | Use it and report what looks wrong |

## Layer 2: it is better than Zen (can only be shown by waiting)

Measured, not claimed. Rule written before the results exist, in [zen-follow-registration.md](zen-follow-registration.md):

- Zen follow ledger (all advices) is the benchmark; Zen calls only is the candidate; unseen window = Zen trades entered after 23 Sep 2026.
- Verdict at the earlier of 30 unseen call spreads or 31 May 2027; fewer than 20 is inconclusive.
- S3n (weekly call spread 100 wide) runs forward in sandbox mode; its first counted week was lost on 5 Nov (PC off); verdict needs 26 trades.
- Even a "supported" verdict earns only a longer shadow run and a January registration, never real money by itself.

## What cannot be done in a day

The forward evidence (weeks to months), a real contract note, a market-hours kill switch test and a first supervised live week. These wait for market days and for the owner.

## Order of work from here

1. Telegram bot on, then daily checks alert the owner's phone.
2. Always-on server decision.
3. Fresh Zen trade file, so the follow ledger can see trades after 23 Sep.
4. Weeks of forward data; weekly public-page reads; verdicts by the written rules.
5. Only then, a staged live start: one lot, Rs 20,000 cap, supervised first week.
