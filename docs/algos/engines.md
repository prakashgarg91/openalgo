# The four engines

| Engine | What it does | Where | Verified how |
| --- | --- | --- | --- |
| Main trading engine | Each trading day, reads the market, builds the day's trade from the chosen algo, sizes it to the loss limit, and starts it in Sandbox (or Live once the gate passes). Decisions are logged. | `services/algos/runner.py` on top of `services/strategy_module/engine.py` | Automated tests with a stand-in broker; the live Sandbox path with real broker data was **not** run here |
| Refine engine | Searches many setups, chooses on early years, checks on middle years, reads the single winner on the last years it never saw. Says "No edge shown" unless it holds up. | `services/algos/builder.py`, run in its own process by `builder_run.py` | Tests, including a pure-noise world (shows an edge 4 percent of the time) and a real run on ten years |
| Debugger | Replays any past day and lists the steps: inputs, kind of day, which rule allowed or stopped the trade, the trade, the modelled result. Also explains the algo's real recorded decisions. | `services/algos/debugger.py`, `Lab` trace hook | Matches the Lab to the rupee on a traded day; names the stopping step on a skipped one |
| Chooser | For today's kind of day, picks an overnight algo only if it made money after costs in the older years AND again in the newer years; otherwise stands aside and says why for each algo. Smart Pick runs this choice through the engine. | `services/algos/chooser.py`, `chooser_store.py` | Tests, a weakened-rule check, and a real table build on ten years |

## What the chooser says on real history today

Built on 2016 to October 2026, split at September 2024, conservative model:

- Zen on calm days: positive in the older years (profit factor 1.39) and Rs -46,241 per lot in the newer years.
- Zen on trending days: marginal older, Rs -45,573 newer. Mirror Zen and Calm Condor lose in both.
- Result: no algo qualifies for any kind of day, so Smart Pick stands aside every day for now. That is the chooser working, not failing. It will start choosing only if an algo earns it.
- Volatile and event days have no trades from any algo (they were designed to stand aside there).

## Limits

- Prices are modelled, not real fills; earlier real-price tests found the models flatter option sellers.
- Smart Pick chooses only among overnight algos (including ones you built), because it enters at the close. Morning Gap is intraday and is not in its pool.
- Smart Pick's Live worst-case figure is 10 percent of capital, the cap every algo is sized to.
- The evidence table is rebuilt by hand ("Refresh the evidence"); it is not scheduled, and the page shows how old it is.
- The Lab refuses Smart Pick, because its choices come from the same history and would look ahead.

## Quality gates run on this work

| Gate | Result |
| --- | --- |
| Linux gthread suite (the CI job's command, 1,467 tests) | First full run: 1 failure, which was mine: the lazy "built algos loaded" flag was an unlocked check-then-act. Fixed with a lock and a barrier test that fails without it. See the final run below. |
| Migrations on a populated copy forced back to the old schema | `migrate_algos.py` and `migrate_phone_login.py` each create only the missing table, leave existing rows alone, are idempotent, and `--status` reports correctly. |
| Resource audit (descriptors, threads, memory) | Static read of every new resource, plus a measurement: 25 consecutive search jobs left file descriptors at 5, threads at 1, zombie processes at 0, and at most 11 job folders. One real gap found and fixed: a failed waiter thread could leave the engine "busy" until restart. |
| Security read | Two findings fixed. (1) A registered number answered slower than an unknown one because the text was sent inside the request; it is now sent in the background. (2) Fresh codes every minute allowed slow guessing; ten wrong guesses an hour on a number now stop new codes and guesses. Each has a test that fails without the fix. |

Not covered: nothing here was run against a live broker, a real SMS provider, or Upstox.
