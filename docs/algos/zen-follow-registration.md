# Zen follow ledger: registration (frozen 6 November 2026, before any unseen Zen trade was read)

This page is written and committed before looking at any Zen trade entered after 23 September 2026. Its commit time is the proof.

## What is being tested

A shadow ledger, no orders, that follows Stratzy's Zen advices at one lot (65 or 75 units, as the advice says), using Zen's published entry and exit prices, with our realistic cost schedule (`services/algos/eod_screen.leg_cost`) and a doubled-cost variant. Two variants:

- **Zen all (benchmark).** Every Zen advice. This is the bar a better idea must beat. It is a benchmark, not a trial.
- **Zen calls only (candidate).** Only Zen's call credit spreads. It counts as one trial (running count 321) and is registered in the idea register in January 2027, because November and December already hold their one idea each. This page is the dated freeze; the register entry cites it.

## Seen and unseen data

- **Seen:** Zen's 216 trades to 23 September 2026. Our reconciliation and the trading-rex-ai studies have looked at them, and the calls-only idea came from that ledger, so any figure on seen trades is descriptive, never evidence for the idea.
- **Unseen:** every Zen trade entered after 23 September 2026. None has been read. The unseen window starts when the trade file is refreshed (the trading-rex-ai agent has been asked to refresh it).

## Frozen verdict rules (calls only, unseen trades only)

Evaluated at the earlier of 30 unseen call spreads or 31 May 2027. Fewer than 20 unseen call spreads is **inconclusive**.

1. Net after our realistic costs, one lot, above zero.
2. Net above zero at twice the costs.
3. Deepest fall of the cumulative result under Rs 20,000.
4. Worst single day above minus Rs 10,000.
5. Deepest fall smaller than that of Zen all over the same trades.

All five met: **supported**. Otherwise **unsupported**. Neither word means Live: the register's own statistical bar (0.025 divided by the running count) is not claimed here, so a supported result only earns a longer shadow run or a place in the January registration, never real money by itself.

## What can go wrong, in advance

- The window may be a rising market, where call spreads lose. Zen's seen window fell 8 percent, which suits call spreads (see [zen-reconciliation-2026-11-06.md](zen-reconciliation-2026-11-06.md)).
- Zen's side and timing rules are not published. Following Zen's advices is following a vendor, not owning a rule. If Zen changes its behaviour or stops publishing, the ledger stops.
- The vendor's prices are unaudited. Where our own candles exist for the day, the ledger is checked against them.
- One lot at a Rs 1 lakh account: Zen's seen results had a deepest fall of about Rs 27,000 for all trades, above the Rs 20,000 limit.

Code: `services/algos/zen_trades.py` (parser), `services/algos/zen_follow.py` and `scripts/algo_backtest/run_zen_follow.py` (the ledger).

## Disclosure added on 6 November 2026 (after the freeze, before reading any unseen trade)

The owner reports that Zen has not been earning in recent weeks. That is a remark, not a number, and it is about the unseen window, so the unseen window is no longer completely blind. The rules above are unchanged. The verdict will be read from the refreshed trade file only, and the remark is not used as evidence for or against calls only.

## Second disclosure, 6 November 2026 (public page, before the refreshed trade file is read)

Stratzy's public Zen page shows Zen's results for the unseen window at monthly and daily level, all trades together with no side or strike: October 2026 +6.38 percent and November 2026 so far -13.89 percent of the Rs 3.2 lakh maximum allocation, one-month return -18.10 percent. So the unseen window for Zen-all is now partly known, and Zen-all has not been earning lately. It cannot show how call spreads alone did. The rules above are unchanged, and the calls-only verdict will still be read only from the refreshed trade file; these public figures are not used as evidence for or against calls only. Source and daily rows: the private data repository, `research/stratzy_zen_public_calendar/`.
