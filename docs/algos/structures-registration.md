# Alternative structures: registered 1 November 2026, before any of them was replayed

Why: every Zen-style variant lost money on the 108 expired weekly Nifty expiries, and the one that earned before costs (selling calls) was a bet on a falling market. An independent review (Opus 5.5, checked against the code and the evidence) proposed four structures that trade less often, cap the loss at what the Rs 20,000 daily limit can bear, and avoid paying for a stop on every trade. This page fixes their definitions, their cost treatment and their pass rules before any is replayed. Nothing here is an expected profit. See [regime-spread-results.md](regime-spread-results.md) and [cost-scenario-results.md](cost-scenario-results.md).

## Data and what it can and cannot prove

The same 108 expiries and 513 sessions, split in the same way (the first 342 sessions, then the last 171). The last third has already been seen, twice, so it is not an untouched test any more. A structure that passes everything below is therefore only a candidate for the forward shadow test on new days (sandbox mode, from the nightly capture); it is never a finding, and no live money follows a pass in this data.

## The four structures (one lot; the lot is 75 before 30 December 2025 and 65 from that date)

All use the entry machine of the earlier tests where not stated otherwise: at-the-money is the 50-point strike nearest the Nifty's 10:14 price, the nearest weekly expiry, candle prices, no entry when the previous session's India VIX closed at 20 or higher or after a gap down of 1 percent or more. A "session before expiry" counts trading sessions in the data, so a holiday does not shift the count by a calendar day.

- **S1, no stop.** Sell the call spread at the money, 250 points wide, at 10:15 on every session the machine would trade. No stop and no reversal. Take profit when the spread's closing value is 10 points or less. Otherwise exit at 15:00 on the next session, or at the last bar of the expiry day if the expiry comes first.
- **S2, weekly iron condor.** One entry a week, at 10:15 on the session two sessions before the expiry session. Sell the call 150 points above the money and buy the call 250 points above that (400 points above the money); sell the put 150 points below the money and buy the put 250 points below that. Hold to the last bar of the expiry session. No stop, no target, no reversal.
- **S3, weekly call spread.** The entry day and the hold of S2, with one call spread sold at the money and bought 250 points above, nothing on the put side.
- **S4, condor timing.** The condor of S2 entered at 14:30 on the session one session before the expiry session instead. Held to the last bar of the expiry session.

A condor's cost is the sum of the costs of its two spreads. A condor's worst loss on one lot is below Rs 19,000 before the credit, inside the daily limit.

## Costs

Every result is reported under both cost scenarios side by side: the conservative model of the project, and the retail-realistic scenario of [cost-scenario-registration.md](cost-scenario-registration.md). A pass is judged on the realistic scenario and its doubled version. No further scenario is added after seeing results.

## Selection period (the first 342 sessions)

All four structures are replayed and none is chosen over another. A structure is a candidate only if it has at least 40 trades and a positive net at twice the realistic costs.

## Held-out third (the last 171 sessions)

Only candidates are carried to the third (the other structures are reported there too and marked descriptive). A candidate passes only if all of these hold: at least 20 trades; net profit above zero at realistic costs and above zero at twice them; worst drawdown marked to market no more than Rs 20,000; no day losing more than Rs 20,000; and a lower bound above zero for the mean daily result by the moving-block bootstrap (block of 5 sessions, the same seed as the earlier studies) at a one-sided level of 0.025 divided by 4 (the four structures), which pays for trying four.

## Always reported

Trades, net before costs, net under each cost scenario, drawdown and worst day, for both periods. Each result split by the direction of the market, using the sign of the Nifty's return over the 20 sessions before entry (known at entry): S3 and S1 are sold calls and are a bet on a falling market, and the split shows how much of any profit sits in falling stretches. Trial count: these four, added to the 12 spread cells, the 36 earlier Zen cells, the three forward rules and the earlier linkage family.

## What a pass and a fail mean

A pass: the structure goes into a forward shadow ledger on new days under a new registration, in sandbox mode, for at least six months before anyone considers money. A fail: that structure is dropped. If all four fail, the conclusion is that the structures tested do not earn after realistic costs in this window, and the next data worth collecting is the measured bid and ask ([bid-ask-snapshots.md](bid-ask-snapshots.md)).

## Limits

Candle fills with no bid and ask; one falling-Nifty window; about 68 weekly entries in the selection period and 34 in the third, so weak statistical power for S2 to S4; a condor's two spreads are priced from the same candles and assumed to fill together; no costs for margin or early assignment.
