# First scheduled Sandbox entry of the ATM 200-wide executor: evidence (18 November 2026)

Read out on 18 Nov 2026 at 18:55 from `log/sandbox_bot_atm200.log`, `db/sandbox_bot_atm200/state.json` and `db/sandbox.db` (read only). Sandbox mode throughout; no order reached the broker.

| Sign-off item | Result |
| --- | --- |
| Entry between 10:15 and 10:20 | Yes: task started 10:16:00, hedge filled 10:16:01, short filled 10:16:03 |
| Order sequence | Bought NIFTY23NOV2625500CE first (limit, 86.90), then sold NIFTY23NOV2625300CE (limit, 163.50) |
| Gates | Expiry 23 Nov (5 days away); previous India VIX close 15.24 dated 17 Nov; no stale note; one lot of 65 |
| Credit basis | LTP credit 77.05 points; fill credit 76.60 points (0.45 short, inside the 6-point flag) |
| Checks | Every 5-minute mark from 09:20 to 15:25 ran (74 of 74, plus 15:30); none missed |
| Alerts | None: no needs-attention, no mismatch, no error in the bot log |
| Spread value during the day | 54.25 to 77.65 points; target (23.89) and stop (192.63) not reached; position held |
| Mode | Analyze at 18:55; the bot refuses otherwise |
| Book | Sold call -65 and bought call +65 open, as expected overnight |

Exit: the time exit is due at the 15:00 check on Thursday 19 November unless the target or stop fires first.

Found on this first day and fixed the same evening:
- The 15:30 summary reported eight false gaps (09:20 to 09:55) because Windows writes the hour without a leading zero before ten. Fixed; the re-run says "clean day".
- The nightly data check read the ETF ledger FOLDER's own time (2 Nov) instead of its newest file (updated 16:00 today), reported the ledger as 384 hours old, and so blocked the 16:30 end-of-day shutdown. Fixed.
- Telegram is still off, so the entry alert and the summary were only written to the log.

Not yet shown: the exit, the booked net against a hand calculation, and the signal-log comparison (the 10:15 bid-ask snapshot for today must be compared with the bot's strikes: bot 25300 / 25500).
