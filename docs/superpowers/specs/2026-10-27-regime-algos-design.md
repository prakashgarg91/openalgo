# Regime algos: catalogue, context feed and Zen / Mirror Zen

Date: 2026-10-27. Status: approved to build (owner delegated all decisions).

## Intent

A trader who wants to start an algo should pick it from a catalogue, enter
capital, see today's market regime and the worst-case loss, and press Start.
The algo must react to the situation (global cues, volatility, gap, trend)
instead of firing blindly every day. Live orders go through the existing
Upstox plugin. Everything starts in Sandbox mode.

Not in scope: a new execution engine, new risk rules, news-text scoring, any
claim about future profit.

## Decisions

- Algos are templates that emit a normal `/strategy` configuration. Orders,
  stops, recovery, scheduling and Sandbox/Live stay in
  `services/strategy_module/`. No second risk evaluator (CLAUDE.md invariant).
- The regime scorer and the template builders are pure functions with no I/O,
  in the style of `services/risk/`, so they are tested with fixed inputs.
- Market inputs are fetched by a thin, fault-tolerant feed. A missing input
  lowers confidence and is shown to the trader. It never silently becomes zero.
- Deploying creates a Sandbox-only strategy (`live_enabled` false). Going Live
  is the existing per-strategy switch and the catalogue shows maximum loss in
  rupees first.

## Modules

| Module | Role |
| --- | --- |
| `services/algos/context.py` | `MarketInputs` -> `RegimeResult` (label, bias, score, reasons, confidence). Pure. |
| `services/algos/templates.py` | Algo registry. `build(algo_id, regime, capital, params)` -> `Plan` (config or skip with reason, max loss). Pure. |
| `services/algos/inputs.py` | Fetches GIFT Nifty, India VIX, Nifty (broker quotes) and US indices, crude, dollar index (public feed). Cached, bounded timeout. |
| `blueprints/algos.py` | Session API: catalogue, regime, preview, deploy. |
| `frontend/src/pages/Algos.tsx` | Catalogue, regime banner, capital input, max-loss preview, Start. |

## Regime

Inputs: GIFT Nifty gap vs previous Nifty close (percent), S&P 500 and Nasdaq
overnight change, India VIX level and change, crude change, dollar index
change, Nifty trend (close vs 20-day average).

Labels:

- `calm`: VIX below 15, absolute gap below 0.4 percent, no global move beyond
  1 percent.
- `trending`: gap or global cues agree in one direction beyond 0.4 percent.
- `volatile`: VIX above 20 or VIX up more than 8 percent, or any global move
  beyond 2 percent.
- `event`: absolute gap above 1.2 percent or VIX above 28. Algos skip.

`bias` is bullish, bearish or neutral from the sign of the weighted cue sum.
`confidence` is the share of inputs actually available.

## Algos (v1)

All index options on NIFTY, product NRML, expiry weekly (monthly if the weekly
is within 1 day), lots from capital and margin per lot.

- **Zen** (overnight hedged credit spread). Sells ATM-side OTM1 and buys OTM4
  on the side the bias favours: bull put spread on neutral or bullish bias,
  bear call spread on bearish bias. Entry 15:05, exit next session 09:45.
  Short-leg stop loss 30 percent of premium, target 90 percent, which is the
  published 1:3 risk-to-reward. Runs on `calm` and `trending` only.
- **Mirror Zen**. The opposite-side spread of Zen for the same day, so the pair
  hedges directional risk. Runs only when the regime is `trending` and
  confidence is at least 0.6, because in a calm market it only doubles cost.
- Next (day 2 and 3): a calm-market iron condor, and a gap-fade intraday
  spread. Each ships with the same skip rules.

## Safety rules

- Skip with a stated reason on `event`, on low confidence (below 0.5), on
  expiry-day afternoon entries, and when capital cannot cover one lot of the
  spread's margin.
- Max loss shown to the trader is computed from spread width, lots and the
  stop loss, in rupees.
- The deploy endpoint refuses `live_enabled`. Live is a separate, existing
  action.
- No profit figure is ever shown without a Sandbox track record behind it.

## Open items to verify while building

1. Overnight runs: confirm the scheduler start and stop jobs across the
   day boundary (entry 15:05 day D, stop 09:45 day D+1, Friday to Monday).
2. Percent risk units on short legs: confirm the engine reads the sl and target
   percent against entry premium for a short position.
3. GIFT Nifty and US index availability on Upstox. The public feed is the
   fallback and is isolated in `inputs.py`.

## Testing

Table-driven tests for the scorer and each template, including skip paths and
the max-loss arithmetic, and one test that every emitted config passes
`validate_strategy_config`. Blueprint tests follow `test_strategy_module_api.py`.
