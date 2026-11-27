# DRAFT pre-registration: skip calm days in the 200-wide call credit spread (27 November 2026)

Status: DRAFT for the owner's yes. Nothing run, no trial counted yet. If approved, this file and its code are frozen
by one commit; a defect found later may be fixed, but the re-run counts as a new trial.

## Why

The 26 Nov research (validation-week1-2026-11.md, section 10) found that the 10:15 at-the-money straddle exceeded the
move to expiry on 71 percent of days when the previous VIX was at or above its trailing 60-session median, and on
59 percent below it, with the straddle about equal to the move on calm days before costs. A public study read on
23 Nov also found option selling lost money in the calmest third of the market. Question: does skipping calm days
improve the frozen 200-wide rule?

## The rule (identical to the frozen 200-wide rule plus one extra skip)

All of services/algos/atm200_rule.py (width 200, VIX gate at 20, credit floor 5, target 31 percent, stop 250 percent,
exit 15:00 next session, lot by expiry), PLUS: skip the day when the previous session's India VIX close is BELOW its
median over the 60 sessions before it (previous sessions only; the median of the closes present). The 60-session
window is the one already used on 26 Nov and is not searched.

## The honest limit of past data

The 5-minute option bars (Oct 2024 to Oct 2026) are the window on which the rule was found, and the calm split was
looked at on 26 Nov. A past replay therefore cannot confirm the idea; it is run once as a DESCRIPTION. Fewer days
also means fewer trades (about half), so its t-statistic will be lower by arithmetic.

## Steps and pass lines (fixed now)

1. One replay on the stored bars with the six timing settings (base, a to e): trades, net realistic and doubled, t,
   worst trade, deepest fall, plus the trades the calm skip removes, on their own. One counted trial.
   Stop sign: if the combined run (e) with the calm skip is no better than the frozen rule's combined run
   (Rs 1,16,092 net) on net rupees AND per trade, the idea is retired; fewer trades with the same or lower profit
   is not an improvement.
2. If it passes step 1: a forward SHADOW ledger (as built for the 100-wide test: no orders, from stored one-minute
   candles), judged after 30 completed trades with the owner's pre-set lines: net positive at realistic costs and
   better per trade than the counted Sandbox bot over the same days. Anything else is a fail.
3. A pass never changes the frozen rule by itself; it is shown to the owner with the evidence.

## What it will not do

Search the window, the gate level or any other setting; touch the frozen rule or its Sandbox bot; place an order.

## Cost and risk

One worker job (GLM 5.3 Flash) to add the skip to the stress replay, one run. The trial count rises to about 362.
Risk: low. The chance of a lucky false find on a half-sample is real; step 1 is a stop sign only, never a pass.
