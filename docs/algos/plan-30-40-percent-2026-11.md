# Plan: 30 to 40 percent a year from F&O on Rs 1,00,000 (owner's goal of 27 Nov 2026)

Round 1 written 27 Nov 2026 after a review by ZCode GLM 5.3 Flash (GLM 5.4 and GPT-6-Astra were unavailable: key refused
and usage limit until 13:08). Round 2 (Astra) follows. General information, not investment advice; the decisions are the
owner's.

## 1. The arithmetic of the rule (70 percent of profit withdrawn, 30 percent kept)

| Gross return | Year 1 profit | Withdrawn | Capital after 1, 3, 5 years | Withdrawn in 5 years |
| --- | --- | --- | --- | --- |
| 30 percent | Rs 30,000 | Rs 21,000 | 1.09L, 1.30L, 1.54L | Rs 1.26L |
| 35 percent | Rs 35,000 | Rs 24,500 | 1.11L, 1.35L, 1.65L | Rs 1.51L |
| 40 percent | Rs 40,000 | Rs 28,000 | 1.12L, 1.40L, 1.76L | Rs 1.78L |

The capital grows only about 9 to 12 percent a year because 70 percent leaves. Rs 6,000 a week (Rs 3.12 lakh a year)
needs about Rs 12 to 15 lakh of capital at 30 to 40 percent. Choose: income (needs capital) or growth (needs low
withdrawals). With Rs 1 lakh, keeping more profit in early years is what builds the capital the weekly figure needs.

## 2. Honest range
Nothing we hold proves 30 to 40 percent. The main rule is t 2.47 in the replay and t 1.59 under combined timing stress
(after about 361 trials), with 2 forward trades at Rs -4,774. Plan on 8 to 15 percent blended, treat 30 percent as a good
year, and treat a loss of 30 to 45 percent of the F&O sleeve as possible (deepest replay fall Rs 38,000 to 45,000).
A public record check found no verified retail 30 to 40 percent.

## 3. The system
- Core (never needs margin): the monthly Nifty ETF / gold ETF / cash dual-momentum ledger, the one family that earned
  on years it had never seen. Run it first; it is the quickest honest real-money result.
- F&O sleeve: the frozen ATM 200-wide call credit spread, ONE lot only (about Rs 57,000 incl. buffer; largest loss
  Rs 6,500 to 9,100). No second lot until capital passes about Rs 1.35 lakh.
- While only Rs 32,041 is funded: no real F&O (one lot does not fit). ETF core on the Rs 32k; spread in Sandbox.
- At Rs 1 lakh: about Rs 60k to the F&O sleeve, Rs 40k to the ETF core.
- Entry day: pre-register one test of expiry-day-only entries (vendor data: premium sellers earned on expiry days).
  Judge once; if it fails, the daily version stays as is; never run both live.
- Rules: no tuning, every idea counted, Sandbox before anything real, stop F&O for the year if the combined forward
  loss on the spread passes Rs 15,000.

## 4. Conflict to settle (owner)
The adopted Rs 5,000 daily budget is below one lot's largest loss (Rs 6,500 to 9,100). The review suggests treating a
stopped trade as the end of that week (the 3-entries-a-week cap already limits it) and keeping the Rs 10,000 pause.
The owner already set Rs 10,000 after 10 profitable closed Sandbox trades.

## 5. Tax and withdrawal (general information)
F&O profit is non-speculative business income at slab rates; advance tax installments fall on 15 Jun, 15 Sep, 15 Dec and
15 Mar once the liability passes Rs 10,000. Audit is unlikely at this turnover (turnover for options is the sum of the
absolute profits and losses plus sell-side premium), but check the limits each year; presumptive taxation exists but
taxes deemed, not actual, profit. Setting aside 30 to 35 percent of net profit for tax and keeping the rest as
expenses and withdrawal is consistent with the 70 percent rule. ETF gains: long-term above 12 months at a lower rate,
otherwise slab. Confirm with a chartered accountant.

## 6. Milestones to March 2027 (go and no-go)
- Dec 2026: ETF ledger running on the Rs 32k; frozen spread in Sandbox; go/no-go file (about 19 Dec). No-go on any
  operational failure.
- Jan 2027: 25 or more closed Sandbox trades; fills within the assumed band; results inside the replay range.
- Feb 2027: 10 closed trades net positive and a go: only then one lot (needs Rs 60k funded), 3 entries a week at most.
- Mar 2027: first honest quarter; pay the 15 Mar installment; continue only if real trades are clean and net better
  than Rs -5,000. Kill line: forward loss above Rs 15,000 stops F&O for the year; the ETF core continues.

## Round 2 (GPT-6-Astra, 27 Nov 2026, 13:10): where it disagrees with round 1, and the final plan

1. A — I disagree with the proposed Rs 60k F&O/Rs 40k ETF split. Margin affordability is not loss affordability. One spread’s observed Rs 9,100 loss exceeds your Rs 5,000 budget; therefore the permitted size is zero lots, even with Rs 1 lakh funded. Its contractual expiry loss is (200 minus net credit) × applicable lot size, plus costs; historical losses are not a ceiling.

Neither 8–15% blended nor 30–40% is established by your evidence. Use 6–10% nominal annually after costs, before personal tax, as a provisional long-term planning assumption for an ETF/cash portfolio—not a forecast. Budget zero trading income through March. After approximately 361 trials, the selected t-statistic is not independent confirmation. Ten profitable trades should not automatically double risk. Keep the owner’s Rs 10,000 pause, not Round 1’s Rs 15,000.

2. B — Automatically unwind an abandoned hedge; waiting 2h45m for a person is an execution-control failure. Start unwinding immediately after confirmed entry abandonment, rather than deliberately waiting minutes.

Use fresh executable quotes and depth; buy the hedge first and verify filled quantity. Submit the short using a marketable limit, constrained by minimum acceptable spread credit. Allow bounded repricing within a proposed 30-second entry deadline. No order type guarantees both execution and price.

On timeout, cancel the short and reconcile cancellations, late fills and actual positions before selling any hedge. Retain protection for any short quantity; flatten confirmed orphan quantity automatically. During ordinary exits, close the short first.

Use marketable DAY limits with explicit cancellation; IOC only if supported for your broker’s F&O API route. Do not assume raw market orders are permitted: [NSE requires algorithmic market-price protection](https://nsearchives.nseindia.com/content/circulars/FAOP69296.pdf). Protected orders can still remain unfilled, so monitor, reprice within approved emergency bounds, alert immediately and disable new entries. [Broker explanation](https://support.zerodha.com/category/trading-and-markets/charts-and-orders/order/articles/market-price-protection-on-the-order-window).

3. C — The ETF core is the strongest candidate you have, conditional on those “never-seen” years genuinely remaining outside selection. Fifteen forward sessions cannot establish expected return.

On Rs 32k, provisionally allocate Rs 25k to the existing monthly rule and Rs 7k to bank cash. At Rs 1 lakh, use Rs 80k for that rule and Rs 20k cash; zero live F&O. These are allocation recommendations, not tested optima.

Freeze the existing lookback, ranking and cash filter. Calculate signals after month-end close; trade next session using liquid ETFs and limit orders, whole units only. Allow the strategy allocation itself to remain in cash. Record costs, spreads, distributions and tax from switches; compare against simple fixed-allocation benchmarks. The 6–10% planning assumption applies here too; losing years remain possible.

4. D — Final plan, ten lines:

1) The two controlling numbers are Rs 5,000 daily risk budget and Rs 9,100 observed one-lot loss: incompatible.
2) November: freeze live F&O and retain today’s orphan loss in the execution ledger.
3) December: test rejected orders, partial fills, late fills, disconnects and automatic recovery.
4) December: start the small ETF allocation only after fixing the monthly rule in writing.
5) January: reconcile every real ETF fill, charge and position against broker records.
6) January: continue frozen spread Sandbox; stop variant searches and vendor-driven selection.
7) February: require zero unresolved positions or unexplained ledger differences before any progression.
8) F&O remains no-go until contractual loss plus costs fits explicitly approved risk limits.
9) March: review forward results against benchmarks; insufficient evidence means continue observing, not scale.
10) Pause at Rs 10,000 cumulative pilot loss; reserve actual tax liabilities before considering withdrawals.
## Reconciled plan (Claude, for the owner's decision)

- Target: 30 to 40 percent a year is not established; Astra plans 6 to 10 percent nominal after costs for an ETF and cash
  portfolio and zero trading income through March. The owner's 40 percent stays the aspiration, judged only by real results.
- F&O: zero live lots while the largest loss of one lot (Rs 6,500 to 9,100) exceeds the approved daily risk budget.
  The owner may raise the budget to Rs 10,000 under the 10-trade condition; Astra advises that ten profitable trades must
  not automatically double risk and keeps the Rs 10,000 pause (not Rs 15,000).
- Core: the monthly Nifty ETF / gold ETF / cash rule. Rs 25,000 of the Rs 32,041 and Rs 7,000 cash now; Rs 80,000 and
  Rs 20,000 cash at Rs 1 lakh. Freeze lookback, ranking and cash filter in writing first; signals after month-end close,
  next-session limit orders, whole units, record every cost and tax. A 6 to 10 percent planning range, losing years possible.
- Execution fix (27 Nov failure): buy the hedge first and verify the quantity; sell the call with a marketable limit and a
  minimum credit; reprice within a 30-second deadline; on timeout cancel, reconcile, then automatically unwind the hedge
  at once (not wait for a person); alert; disable new entries. Test rejected, partial and late fills in December.
- Process: stop variant searches and vendor-driven selection; keep the frozen spread in Sandbox; reconcile every real
  ETF fill and charge; withdraw nothing before actual tax liabilities are reserved.
