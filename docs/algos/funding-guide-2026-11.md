# Funding guide for the one-lot pilot (23 November 2026)

Plain notes for the owner. The pilot is the owner's own decision; nothing here is investment advice.

## What one lot needs

The Algos page card "Funds for the pilot" reads it live from Upstox (read only). On 23 Nov 2026, for the
01 Dec 25600/25800 call spread:

| | Rupees |
| --- | --- |
| Margin after the hedge benefit | 40,677 |
| Bought call premium | 12,506 |
| Safety buffer (larger of Rs 3,000 or 10 percent of margin) | 4,068 |
| Total needed | 57,250 |
| Cash in Upstox | 32,041 |
| Short by | 25,209 |

The need moves with the market and the strikes: about Rs 50,000 to 60,000 for one lot so far.

## Steps

1. Add the shortfall plus a little room (about Rs 26,000) to the Upstox account.
2. Open OpenAlgo, Algos page, press "Check again" on the card. It should say "You have enough for one lot."
3. Tell Claude. Nothing changes automatically: the app stays in Analyze mode and the Live gate stays on.

## What funding does and does not change

- It makes the manual pilot possible: the owner places each one-lot trade by hand, one position at a time,
  with the pilot pause at a cumulative loss of Rs 10,000.
- It does not switch anything to Live, and the AI never places a real order.
- The automatic executor stays unused until the Sandbox sign-off (three more clean cycles) and the
  owner's written word.

## What one lot can lose

A 200-wide spread at lot 65 can lose up to about Rs 13,000 less the credit in one trade. The deepest fall
in the seen-data replay was Rs 43,723 over a run of trades. Two lots double both.
