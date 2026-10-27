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
| `services/algos/templates.py` | Algo registry (Zen, Mirror Zen, Calm Condor, Morning Gap Fade; each has its own check time). `build(algo_id, regime, capital, params)` -> `Plan` (config or skip with reason, max loss). Pure. |
| `services/algos/pricing.py`, `services/algos/lab.py` | The Lab: replay any algo over real history, with a standard and a conservative option-price model, and (optionally) actual NSE option prices. Pure except `load_history`. |
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

## Open items (status after day 2)

1. Overnight runs: resolved. The engine cannot save an overnight start and stop
   pair (the validators require start before stop). So the strategy is
   positional with no `entry_time`, and its `exit_time` of 09:45 installs a
   weekday square-off job with no scheduler config (pinned by a test). The
   entry is owned by `services/algos/runner.py`: a 15:05 weekday cron job on the
   strategy scheduler re-scores the market on fresh data, rewrites the legs for
   the chosen side and lots, and starts a normal run.
2. Percent risk units on short legs: resolved by reading
   `services/strategy_module/risk_adapter.py`. A percent is a percent of the
   entry price, so a 30 percent stop on a short leg sits 30 percent above the
   sold premium.
3. GIFT Nifty and US index availability on Upstox: still open. The Zen entry
   at 15:05 uses Nifty's move since the previous close, so GIFT Nifty is not
   needed for these two algos; it matters for morning-entry algos. US indices,
   crude and the dollar index come from the public feed in `inputs.py`.
4. Upstox token expiry: an overnight position needs a fresh Upstox login before
   the 09:45 exit, because broker tokens expire around 3 AM. The page must say
   so before a Live start.

## Safety additions made while building

- Going Live needs `confirm_max_loss` equal to the worst-case rupee loss shown.
- A deployment never starts a second run while the previous position is open.
- A market holiday, a missing API key, a missing lot size and an engine refusal
  are each recorded as a plain-language decision, never raised.

## Testing

Table-driven tests for the scorer and each template, including skip paths and
the max-loss arithmetic, and one test that every emitted config passes
`validate_strategy_config`. Blueprint tests follow `test_strategy_module_api.py`.
