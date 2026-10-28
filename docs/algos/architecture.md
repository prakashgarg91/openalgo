# Architecture of the Algos feature

The illustrated diagrams on docs.openalgo.in live in the separate `openalgo-docs` repository, which this
session could not reach. These are the same flows as Mermaid text, so they can be turned into those
images later. The other repository is untouched, and its diagrams are still the old ones.

## Components and who talks to whom

```mermaid
flowchart LR
  subgraph Browser
    UI[Algos page: Discover, My algos, Build, Test, Why]
    Login[Login: password or phone code]
  end
  subgraph Flask["Flask app (one worker)"]
    BP[blueprints/algos.py]
    PH[blueprints/phone_login.py]
    RUN[runner: daily entry]
    CH[chooser + Smart Pick]
    LAB[lab + debugger]
    SCH[APScheduler jobs]
  end
  subgraph Own process
    BR[builder_run: search, chooser table, weekly maintenance]
  end
  ENG[strategy_module engine]
  BRK[Upstox via broker plugin]
  FILES[(db/algo_chooser, db/algo_builder)]
  DB[(openalgo.db: algo tables, phone_login)]
  Y[Yahoo daily history]
  UI --> BP
  Login --> PH
  BP --> RUN
  BP --> CH
  BP --> LAB
  BP -- starts --> BR
  SCH -- daily 15:05 --> RUN
  SCH -- Sunday 10:07 --> BR
  RUN --> CH
  RUN --> ENG
  ENG --> BRK
  BR --> FILES
  CH -- reads --> FILES
  LAB --> Y
  BR --> Y
  BP --> DB
  RUN --> DB
```

Ports and the market-data pipeline (5000, 8765, ZeroMQ 5555) are unchanged. The search runs in a separate
process on purpose: inside the single web worker it would stall every request and order for a minute.

## One day in the life of an algo

```mermaid
sequenceDiagram
  participant S as Scheduler 15:05 IST
  participant R as runner.run_entry
  participant C as chooser (Smart Pick only)
  participant E as strategy engine
  participant B as Broker
  S->>R: run_entry(deployment)
  R->>R: read market, score the kind of day
  alt market closed, data thin, or position still open
    R-->>R: log "sat out" with the reason
  else
    opt Smart Pick
      R->>C: which algo has earned today?
      C-->>R: one algo, or stand aside
    end
    R->>R: build plan, size to the loss limit
    R->>E: rewrite legs, start run (Sandbox unless Live gate passed)
    E->>B: orders (Live) or sandbox fills
    R-->>R: log the decision
  end
```

## How an algo gets chosen and refined

```mermaid
flowchart TD
  H[Ten years of history] --> L[Lab replay with costs]
  L --> T1[Builder: choose on early years]
  T1 --> T2[Check on middle years]
  T2 --> T3[Read ONLY the winner on last years]
  T3 --> V{Held up on both?}
  V -- no --> N[No edge shown]
  V -- yes --> P[Candidate: Sandbox first]
  L --> TB[Evidence table: per algo, per kind of day, older vs newer]
  TB --> Q{Made money in both periods?}
  Q -- yes --> PICK[Chooser picks best average]
  Q -- no --> ASIDE[Stand aside, with reasons]
  W[Weekly pass] --> TB
  W --> RV[Re-check built algos: proposal only]
```

## What is stored where

| Thing | Where |
| --- | --- |
| Deployments, decisions, built algos | `openalgo.db` tables `algo_deployment`, `algo_decision`, `algo_custom` |
| Phone number for sign-in | `openalgo.db` table `phone_login` |
| Chooser evidence | `db/algo_chooser/table.json` |
| Search jobs and weekly proposals | `db/algo_builder/` (last 10 jobs kept, plus `proposals.json`) |
| Cached history | `db/algo_lab/` |
