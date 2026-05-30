# Agentic QA — Explorer + Judge

An agent swarm that explores a web app, finds broken flows, and judges its own
results. An **Explorer** agent drives [Parabank](https://parabank.parasoft.com)
(a demo online bank) through Playwright tools and records what happened; a
separate **Judge** agent scores each completed flow with a structured verdict.
A **LangGraph** orchestrator routes explorer → judge → report and loops to the
next flow.

The two agents are deliberately separate: the explorer is biased toward "I made
it work," so an independent judge provides the real assessment — and a cheaper
model can drive exploration while a stronger model judges.

```
            +-------------------+
            |  Parabank (:8080) |   system under test
            +-------------------+
              ^               |
       observe|               | drive (Playwright tools)
              |               v
  +-----------------------------------------------------------+
  |  LangGraph orchestrator (shared QAState)                  |
  |                                                           |
  |   explorer_node --bundle--> judge_node --verdict--> report_node
  |  (LLM + Playwright)        (LLM + rubric)          (md + html)
  |        ^                                              |    |
  |        +------------------ next flow -----------------+    |
  +-----------------------------------------------------------+
```

## Why it's built this way

- **Page state = accessibility tree, not raw HTML.** `get_page_state` returns
  roles, labels, and visible text — compact and token-cheap. Each interactive
  element is tagged with a stable `data-aqa-ref` so the agent gets an actionable
  selector off the a11y view.
- **Self-healing intent.** A failed action isn't fatal: the explorer records the
  error, re-snapshots, and re-plans. Flows end on goal-completion, a step
  budget, or N consecutive unrecoverable failures.
- **Structured verdicts.** The judge returns a typed Pydantic `Verdict`
  (status / category / severity / reasoning / confidence) — storable, countable,
  regression-testable.
- **Offline-replayable.** The judge scores recorded observation bundles, so the
  whole evaluation path is unit-tested with a fake LLM (no network, no key).

## Quickstart

```bash
# 1. Run Parabank locally (stable + repeatable; public host resets periodically)
docker run -d --name parabank -p 8080:8080 -p 61616:61616 -p 9001:9001 parasoft/parabank
#    wait ~30s, then http://localhost:8080/parabank/index.htm should load

# 2. Install
uv venv --python 3.13
uv pip install -e ".[dev]"
uv run playwright install chromium

# 3. Provide an LLM key
export OPENAI_API_KEY=sk-...

# 4. Run QA
agentic-qa list-flows
agentic-qa run --flows transfer,billpay        # or just: agentic-qa run
agentic-qa history                             # aggregate stats across runs
```

### RAG-grounded judge (optional)

Ground each verdict in documented expected-behavior notes ("a transfer must
reduce the source balance") instead of the model's prior. Backed by pgvector,
with an automatic in-memory fallback if Postgres isn't reachable:

```bash
docker run -d --name aqa-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=agentic_qa \
  -p 5433:5432 pgvector/pgvector:pg16
uv pip install -e ".[rag]"
agentic-qa run --flows transfer --rag
```

Each run writes to `runs/<timestamp>/`:
- `<flow>.json` — the full observation bundle (actions, final state, errors)
- `<flow>_final.png` — final-page screenshot
- `report.md` / `report.html` — flows tested, verdicts, and bugs found

## Testing

```bash
pytest                 # fast unit tests (no key, no server) — 'slow' tests skipped
pytest -m slow         # end-to-end against live Parabank + OPENAI_API_KEY
```

The unit suite validates the tool layer, the self-healing explorer loop, the
judge (against recorded good/broken fixtures), the report renderers, and the
LangGraph wiring — all deterministically with a scripted fake LLM.

## Project layout

```
src/agentic_qa/
  config.py        target URL, models, run settings (lazy key)
  auth.py          idempotent Parabank login/registration
  tools.py         Playwright actions as typed tools + console/network capture
  schema.py        Action / ExplorerDecision / StepRecord / ObservationBundle / FlowSpec
  llm.py           injectable OpenAI structured-output client + token accounting
  explorer.py      observe -> decide -> act -> record, with self-healing
  judge.py         Verdict schema + judge(bundle) -> Verdict
  flows.py         default Parabank flows
  graph.py         LangGraph wiring + QAState
  report.py        markdown + HTML report renderers
  cli.py           `agentic-qa` entry point
tests/             unit tests + recorded fixture bundles
docs/superpowers/specs/   design doc
```

## Build phases

Built incrementally (see `docs/superpowers/specs/`): 0 skeleton → 1 tools →
2 explorer → 3 judge → 4 LangGraph → 5 suite + CLI + report → 6 SQLite history →
7 RAG-grounded judge → 8 planted-bug demo.
