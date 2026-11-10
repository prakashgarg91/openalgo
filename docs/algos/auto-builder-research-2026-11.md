# Auto builder: what online research says, and what we built (10 November 2026)

The owner asked for an "auto algo builder that builds profitable algos on its own and improves recursively". Research first, then the build. Reading the sources changed the goal, and this page records how.

## What the research says

- A loop that proposes, tests and refines strategies runs many hidden backtests. In one study the agent's best strategy had a Sharpe of 1.69 after 102 trials and 0.18 on held-out data; in five repeated runs, none survived ([arXiv 2608.27734](https://arxiv.org/pdf/2608.27734)).
- The sources agree on the defence: count every trial in a ledger, correct for the number of trials (Deflated Sharpe Ratio, backtest-overfitting probability, reality checks), validate walk-forward, and keep a held-out window that the search never sees ([survey](https://arxiv.org/html/2605.19337v1), [walk-forward framework](https://arxiv.org/pdf/2512.12924)).
- Serious systems separate proposing from judging, with sealed evaluation data ([AQuA](https://arxiv.org/pdf/2608.12841), [Agora](https://arxiv.org/pdf/2606.29194)).
- Memory helps: a knowledge base of past ideas and a known-alpha prior cut invalid ideas ([multi-agent alpha miner](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6906675)).
- Attrition is the norm: about 5 in 200 generated strategies survive walk-forward ([guide](https://quanttradingtools.com/automated-trading-strategy-generation/)).
- No independent, rigorous study of Nifty weekly credit spreads was found. Vendor pages do not model slippage or costs.

## What this changed

The goal "builds profitable algos on its own" is not claimed. An automatic search that keeps what looks best mostly finds luck. The platform already has the defences the research asks for (a trial register with a bar of 0.025 divided by the count, one idea a month, a held-out last third, a locked live gate). The Auto builder tab is therefore a disciplined idea tracker, not a profit finder.

## What the tab shows (read only)

`GET /algos/api/idea-tracker`, built in `services/algos/idea_tracker.py` from the register's own records:

1. Every idea, where it stands, and which of its own gates it missed.
2. The memory of failures: gates missed most often. Read it before proposing the next idea.
3. The hurdle: the number of standard errors a result must be above zero given how many ideas were tried (the normal quantile of the register's bar). It is a restatement of the existing bar, not a new rule.
4. The forward shadow ledgers, and the live gate (always shown locked).

It has no Deploy, Run or Kill Switch control, proposes nothing and places no order.

## Not done, on purpose

- No automatic idea generation. A generator without an outside judge and a fixed trial budget is the failure mode in the first bullet. If one is added later it must write only registrations (one a month), never run them, and never see the held-out window.
- No Deflated Sharpe per idea yet: it needs each idea's return series, which the register does not store. Candidate for a later change.
