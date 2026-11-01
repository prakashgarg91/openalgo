# C1, the month-end ETF window: registered 1 November 2026, before any forward day

Why: the owner asked for new algos in the vibe-trading way (idea in chat, rules written down first, tested, then sandbox). GPT-6.1 Sol proposed four ideas and Opus 5.5 reviewed them. Opus judged the long strangle, the expiry-day butterfly and the equity-gold snapback to be traps (the first buys the variance premium our own tests found real but that failed its expected-premium gate; the second depends on slippage we have not measured yet; the third rests on two numbers chosen by eye and would fire only a few times), and approved this one because the turn-of-month effect is published and was not found in our data. This is cheap forward evidence, not a claim of beating anyone.

Nothing here places an order. It is a shadow ledger (the same accounting as the other ETF ledgers, see [idea-registration.md](idea-registration.md)).

## Question

Does holding the Nifty ETF only from three sessions before a month's last session to the third session of the next month earn more than passive equity exposure of the same size, after retail costs?

## Rule (every number fixed)

- Start with Rs 1,00,000 in cash, earning nothing. Trade only NIFTYBEES, whole shares.
- Buy at the close three sessions before the month's last session. Spend at most Rs 19,000 including entry charges (the ledger buys Rs 18,900 of shares and the charges come to about Rs 40).
- Sell everything at the close of the third session of the next month.
- No filter, no second entry, no leverage, no discretionary change. The decision uses the calendar only, no price.
- The month's last session is read from the stored sessions, so the ledger shows an entry once the next month's first session is stored. A missing price invalidates that month; dates are not shifted.

## Costs

The repo's frozen itemised schedule (`services/algos/universe.py`, frozen as of 29 October 2026) and its doubled variant, with whole-share sizing redone in each variant. This replaces the simplified Rs 20 plus 0.15 percent per side in the first draft of the plan, because it is the schedule every other ledger uses. Closing prices do not establish executable fills.

## Data and what is untouched

All history up to 6 November 2026, including all 108 option expiries, is development data and can confer no pass. A 15-year screening is run once for information. Confirmation data is the forward sessions only.

## Trials

This registration is trial 311 (see [TRIAL_REGISTER.md](TRIAL_REGISTER.md)). Every alternative window, filter, cost change or post-result revision adds another trial and starts a new version.

## End and gates

Assessed once, after 24 valid monthly trades or on 31 May 2029, whichever comes first; fewer than 24 is inconclusive. All of these must hold:

- positive net under both cost variants;
- maximum drawdown and worst day each no more than Rs 20,000 (the cap on exposure makes this nearly automatic; it is not a guaranteed stop);
- still positive after removing the best month;
- positive excess over an exposure-matched passive NIFTYBEES hold (sized by C1's mean invested rupees across all forward sessions) under both variants;
- a positive one-sided bootstrap lower bound on the mean monthly excess at significance 0.025 divided by 311, moving blocks of 3 months, 100,000 draws, seed 20261101.

Stop rule: cumulative baseline net at or below minus Rs 5,000 ends C1 permanently. No early promotion, and no combining with S3n's positions.

## Limits

About 24 monthly observations can show an effect of a few percent a year only if it is very regular. The result will probably be inconclusive. If both this and the S3n forward test (registered separately) end without a pass, the owner's default is a simple equity-plus-gold holding with at most Rs 20,000 invested, which caps exposure but is not a guaranteed daily stop.
