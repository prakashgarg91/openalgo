# Domino chain test: registered 31 October 2026, before any chain result was computed

Question: does a foreign move travel to the Nifty through an Indian sector or stock, and does that middle step predict what the Nifty does after the open? The pair study ([linkage-study-results.md](linkage-study-results.md)) found that foreign markets explain the opening gap but not the move after it. A chain tests the one place left for information to hide: the stocks and sectors that react to the foreign move at the open, and whether the Nifty has caught up with them. Nothing here is an expected profit.

## Data checked before registering (no result was looked at)

- Opening prints are real for the ten sector indices (Bank Nifty, Auto, Energy, FMCG, Infra, IT, Metal, Pharma, PSU Bank, Realty; sector series start in 2010 or 2011) and for 19 heavyweight stocks (Tata Motors returned no data).
- Nifty Financial Services and Nifty Media have one row each and are left out.
- The India VIX open equals the previous close on about 90 percent of days, so it is stale and is not used as a middle step. This also means model 2 of the range study (which added the VIX open) did not test a real VIX open; that finding is withdrawn in the range results.

## Chains

X, the foreign driver, is known before the Nifty opens (same timing rule as the pair study): US markets, US futures, currencies, commodities, Asia, Europe, overseas funds. M, the middle step, is the relative opening gap of a sector or stock on day D: its own gap (open over previous close, in log terms) minus the Nifty's gap, known at 09:15. Gaps beyond 12 percent are treated as missing. T, the end, is the Nifty's move from open to close, and the day's range.

- Stage 1: M on X. Stage 2: T on M.
- Same split as the pair study: first half to 19 July 2017 is discovery, the rest is verification. Each pair needs 500 days in both halves.
- Each stage uses the same test as before: slope with a Newey-West t-statistic, Benjamini-Hochberg at 5 percent over every pair tried in the stage, then verification needs the same sign and a t-statistic of at least 2.
- A chain X to M to T is counted only if both stages verify. For each chain the indirect effect is the product of the two verification slopes, and a mediation check re-fits stage 2 with X in the model; the chain is "carried" if the M effect still has a t-statistic of at least 2.
- Chance reference: the verification targets of each stage are shuffled in blocks of 20 days, 1,000 times; the share of selected pairs that verify by luck is reported.

## Reported

Pairs tried in each stage, how many selected, how many verified, how many chains, how many carried, the top chains, and the plain result for stage 2 on its own (does any sector or stock gap, relative to the Nifty, predict the Nifty after the open at all). If no chain verifies, that is the finding.

## Limits

Open to close includes the first hour, which a 10:15 entry cannot trade, so any effect found is an upper bound on what an entry could use; a follow-up with hourly bars (about two years) would be needed to test it properly. Daily bars cannot tell cause from timing within the day. Yahoo opening prints for sector indices are the exchange's first print and are not independently checked. No news, flows or GIFT Nifty.
