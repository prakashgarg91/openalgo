# Narrower call-only structures: registered 1 November 2026, before either was replayed

Why: the two call-only structures of [structures-registration.md](structures-registration.md) earned money under realistic and doubled costs in both periods ([structures-results.md](structures-results.md)), but their drawdown on one lot (Rs 26,601 and Rs 26,723 in the last third, Rs 50,265 and Rs 31,881 in selection) is above the Rs 20,000 loss limit, and their statistical bound was below zero. One lot is the smallest size, so size cannot be reduced. The one lever that remains, and that can be fixed from risk arithmetic alone, is the width of the wing. Nothing here is an expected profit.

## The rule that sets the width, written before any narrower result exists

The worst loss of one trade is about the width times the lot. A run of two worst-case trades should fit inside the Rs 20,000 limit: 2 x width x 75 <= 20,000 gives a width of at most about 133 points, so the width is 100 points (the largest strike multiple of 50 that satisfies it). That is the only width tried. It was derived from the loss limit, not from any result at 100 points, and no other width will be tried in this branch: a width found by searching a ladder on a window already seen twice would be curve fitting.

## The two variants

- **S1n:** S1 with a 100-point wing. Sell the call spread at the money, 100 points wide, at 10:15 on every session the machine would trade, no stop, no reversal, take profit when the spread's closing value is 10 points or less, otherwise exit at 15:00 the next session or at the last bar of the expiry day. Same filters.
- **S3n:** S3 with a 100-point wing. One weekly call spread, sold at the money and bought 100 points above, entered at 10:15 two sessions before the expiry session, held to the last bar of the expiry session.

Nothing else changes: the same data, the same split (first 342 sessions, then the last 171), the same two cost scenarios, the same costs, lot sizes and slippage assumption.

## Pass rules

The same gates as for the first four, judged on the realistic scenario: in selection at least 40 trades and a positive net at twice the realistic costs; in the last third at least 20 trades, a positive net at realistic costs and at twice them, a worst drawdown marked to market no more than Rs 20,000, no day losing more than Rs 20,000, and a lower bound above zero for the mean daily result by the moving-block bootstrap (block of 5 sessions, same seed). The one-sided level is 0.025 divided by 6, because six structures have now been tried on this data (the four of the first registration and these two), so a pass here pays for the whole family.

## What the result means, fixed now

The last third has been seen twice and the first registration's results for the 250-point versions were known when this width was chosen, so this is not an independent test. A pass means only that the structure may go into a forward shadow ledger on new days, in sandbox mode, for at least six months before anyone considers money. If neither passes, the call-only family does not meet the loss limit and the statistical bar on this data, and the next useful data is the measured bid and ask. Results will be reported for both periods and both cost scenarios, with the split by the sign of the Nifty's return over the previous 20 sessions, as before.

## Limits

A narrower wing earns a smaller credit, so costs and the assumed slippage are a larger share of it; the result may be negative for that reason alone. Candle fills, one window in which the Nifty fell overall, about 67 weekly entries in selection and 30 in the last third for S3n.
