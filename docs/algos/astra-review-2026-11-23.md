# GPT-6-Astra review of the overall plan and the bulk-screen draft (23 Nov 2026)

Asked through Codex (model gpt-6-astra; gpt-6.2-astra is not offered on this account). The brief sent is reproduced at the end. Advice to weigh, not a decision.

## Answer

1. Rs 1,000 daily is not a credible planning target.

That is 21% monthly on Rs 1 lakh, approximately 885% annually compounded. Nothing presented supports it. The best rule’s Rs 430 per trade is a selected, already-inspected estimate, not expected forward income; t = 2.39 fails your stated selection bar.

Budget for zero trading income and possible losses. If an edge eventually survives independent validation, 0.5–2% monthly averaged over years could be a planning scenario—not a forecast—with losing months and substantial drawdowns. That means Rs 500–2,000 monthly on Rs 1 lakh, not daily. Current evidence cannot establish even that range.

The “one in five” estimate is subjective unless backed by a calibrated model. Mechanical Sandbox success provides no evidence about profitability.

2. The screen needs tighter statistical and data boundaries.

Data: EOD futures OI cannot test intraday confirmation in #14. Historical constituent-bank and Bank Nifty data are not explicitly listed. EOD option prices cannot establish intraday spread stops, targets or executable simultaneous fills. November quotes cannot validate historical liquidity. Missing FII/DII flows are not the main obstacle.

Timing: Use each field only after its actual availability. Lag published EOD OI; align US sessions, holidays and daylight saving. Estimate the US-gap relationship using preceding data only. Define “250% stop” precisely: spread price reaching 2.5 times entry credit, or loss reaching 2.5 times credit?

Windows: A previously touched holdout is not pristine. Audit what earlier studies revealed about 2025–26; freezing rules now cannot erase that knowledge. Likewise, reserving 2019–21 now does not make it untouched. Purge trades crossing split boundaries. Account for historical contract specifications and expiry changes, including Nifty’s move to Tuesday. [NSE circular](https://nsearchives.nseindia.com/content/circulars/FAOP68747.pdf)

Testing: BH at 10% controls expected false-discovery proportion under appropriate assumptions; it does not give each survivor a 90% probability of being real. Correlated signals need dependence-aware treatment. Restarting BH nightly gives no overall error guarantee. Use a finite registered research budget or a valid online testing procedure. Correct across all holdout candidates too.

The roughly 3.8-standard-error bar assumes valid p-values. Overlapping holdings, serial dependence and skewed option losses require robust inference, such as a suitable block bootstrap. Repeated forward-ledger checks also need sequential control.

Measures: Predefine direction, horizon, tolerance for “near,” primary statistic and trade conversion. Compare pinning against equally nearby placebo strikes. Forty observations is not a power calculation. Report net expectancy, confidence intervals, drawdown, expected shortfall and capital utilisation—not merely hit rate or underlying points.

3. Cut the first batch substantially.

Drop #3 max pain, #4 pinning and #5 single-strike OI spikes as trading candidates: proximity to strikes is easily confused with prediction. Drop #8’s dealer-gamma interpretation: public OI does not identify dealer positions or their sign. Defer #14 until intraday OI exists.

Deprioritise #1, #2 and #9: OI alone does not identify informed bullish or bearish positioning. Deprioritise #12 and #18 until constituent overlap and market exposure are removed; banks already drive Nifty. Drop #17 from this first batch because sparse calendar effects invite selection.

Retain #6, #7, #13, #15 and #16 as exploratory hypotheses, with frozen definitions. None has earned trading status.

Instead, prioritise two economically grounded questions:

First, does expiry-matched implied variance exceed subsequently realised variance enough to cover executable costs and tail losses? India VIX measures approximately 30-day volatility, so it is not a direct weekly-option substitute. [NSE methodology](https://www.nseindia.com/static/products-services/indices-indiavix-index)

Second, does the proposed signal improve the same spread traded without the signal, at matched exposure? This distinguishes signal value from ordinary short-volatility exposure.

Also evaluate scheduled-event exclusions as risk controls, without searching many calendars.

4. Spend four weeks establishing trustworthy economics and execution.

Week 1: Freeze the main rule, reconcile every replay trade, audit timestamps, cost schedules, spread valuation, overlapping positions and margin assumptions. Resolve the capital/risk contradiction.

Week 2: Complete the remaining three clean Sandbox cycles when signals occur. Test restart recovery, duplicate-order prevention, stale quotes, partial fills, hedge failure and emergency exit. Four clean cycles establish limited operational evidence only.

Week 3: Run one prespecified execution stress analysis and the unconditional-spread comparison. Continue collecting timestamped bid/ask data. Do not retune after seeing results.

Week 4: Produce a go/no-go dossier: available capital, maximum contractual loss, conservative liquidation costs, operational failures and an unchanged forward ledger.

Rs 27,000 daily risk is 27% of proposed capital and 84% of current cash. Reject it. The Rs 10,000 cumulative pause can be breached by one spread loss. Size against maximum loss, not margin. If one lot exceeds the owner’s affordable risk budget, postpone.

A funded, explicitly authorised manual pilot can measure real execution; it cannot establish an edge in four weeks.

5. Stop expanding the search while validation is unfinished.

Stop the nightly new-idea factory, daily-income target and automatic escalation from significance to trading. Archive the failed vendor decider. Keep the January library frozen.

Preserve Sandbox-only automation. Funding solves affordability, not profitability. The fastest honest result may be a documented no-go.
## Brief sent

# Review request: personal Nifty options algo plan (owner: one retail trader, India)

You are asked for direction, as a senior quant reviewer. Be direct and specific. No code changes; reply in plain text.

## Goal and constraints
- Owner wants small, repeatable profit after costs from Nifty weekly options. Aspiration: about Rs 1,000 a day after
  costs on Rs 1,00,000 (about 21 percent a month); would scale to Rs 2,00,000 and more if it works.
- Platform: self-hosted OpenAlgo with Upstox. Everything automatic runs in Sandbox (simulated) mode. The AI never
  places real orders. A one-lot manual pilot is postponed until funding: one lot of the main rule needs about
  Rs 57,250 (hedged margin 40,677 + bought premium 12,506 + buffer); real cash is Rs 32,041.
- Daily loss cap Rs 27,000; pilot pause at cumulative -Rs 10,000.

## Evidence so far
- About 359 ideas tried and counted in a trial register; pass bar is significance 0.025 divided by the trial count
  (now about 3.8 standard errors).
- Best rule: ATM 200-wide Nifty call credit spread, enter 10:15, 1 to 6 days to expiry, skip when previous VIX
  close is 20 or more, credit over 5 points, target 31 percent of credit, stop 250 percent, exit 15:00 next session,
  lot 65. Replay on data already looked at: 388 trades, net Rs 1,67,102 after realistic costs (about Rs 430 a trade,
  t = 2.39), worst trade -Rs 8,935, deepest fall Rs 43,723. A director estimate put the chance it stays net positive
  forward at about 1 in 5.
- Live Sandbox: first full cycle 18 to 19 Nov 2026 worked mechanically end to end (entry, hold, time exit, ledger,
  alerts, fills within Rs 42 of screen prices) and lost Rs 2,954 net. Needs three more clean cycles before sign-off.
- A "vendor decider" (pick the recently best of 24 public vendor algos per volatility cell, walk-forward) was
  pre-registered and run once on 19 Nov: FAIL, t = -0.10; following all 24 equally +49.8 points (t 0.92).
- An in-app Research study of 292 cross-market links: 87 found on 2008 to 2017, 42 held up on 2017 to 2026,
  23 reversed. The US close explains about 24 percent of the opening gap but not the move after the open.
- An end-of-day option library (5 spreads, low-volatility cell only, walk-forward) is pre-registered as a draft for a
  single run in January 2027.

## The new draft to review: daily bulk screen for "missing links"
Data held: NSE end-of-day Nifty futures and options with open interest 2019 to Oct 2026; Nifty daily and 5-minute
bars; global markets daily; India VIX; one-minute option candles from Oct 2026; bid-ask snapshots from Nov 2026;
news headlines from Nov 2026 only. Not held: FII and DII daily flows.
Windows: discovery Apr 2021 to Dec 2024; held back Jan 2025 to Oct 2026 (touched once, frozen rules only);
Feb 2019 to Mar 2021 reserved for the end-of-day library.
First batch, 16 ideas, one fixed setting each:
1 futures build-up type (price and OI up, etc.) -> next session; 2 put-call OI ratio top or bottom tenth -> next
session; 3 distance from max pain on expiry eve -> expiry-day move toward it; 4 expiry close vs largest-OI strike
(pinning); 5 one strike's OI jumping to 3x its 20-day average -> next session's high or low near it; 6 futures volume
in top tenth with price change under 0.2 percent (absorption) -> next session; 7 opening gap far larger than the US
close explains -> fade by 11:00; 8 gamma wall (largest gamma x OI strike) -> next session high or low near it;
9 OI centre moving 100 points or more in a day -> next session; 12 two largest banks moving against Nifty -> next
session; 13 VIX up over 15 percent in a day -> next two sessions; 14 15-minute opening-range breakout confirmed by
rising futures OI; 15 expiry-day move over 0.6 percent by 13:00 -> move to the close; 16 gap over 0.5 percent with
VIX under 15 -> fill by close; 17 pre-holiday and post-holiday sessions; 18 Bank Nifty vs Nifty divergence over
1 percent -> next session.
Rules: fewer than 40 signal days is reported, not judged; batch judged with Benjamini-Hochberg false-discovery control
at 10 percent; survivors become one frozen trade rule with realistic and doubled costs, run once on the held-back
window; passing earns a Sandbox forward ledger judged at the register bar; never Live from a screen. Every idea counts
as a trial; nothing tuned and re-run. Workers write each idea as a tested signal function; a nightly job runs new ideas.

## Questions
1. Is Rs 1,000 a day after costs on Rs 1,00,000 a realistic target for this kind of approach? What is a realistic range?
2. What is wrong or weak in the bulk-screen design (data, windows, multiple-testing control, measures, leakage)?
3. Which of the 16 ideas would you drop, and which better-founded ideas for Nifty options would you add instead?
4. Given the evidence, what should the next 4 weeks focus on to reach a first honest real-money result soonest?
5. Anything in the overall plan you would stop doing?
Answer in under 900 words, numbered to match.
