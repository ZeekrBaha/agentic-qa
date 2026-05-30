# Agentic QA — Explorer + Judge — Design

Date: 2026-05-30
Status: Approved for build (all phases, pause only on failure)

## 1. Purpose

Autonomous QA system: an **Explorer** agent drives a real banking web app
(Parabank) through Playwright tools and records what happened; a separate
**Judge** agent scores each completed flow with a structured verdict; a
**LangGraph orchestrator** routes explorer → judge → report and loops to the
next flow. Portfolio target: "Agentic QA / AI Quality Engineer" — autonomous
exploration, self-healing intent, LLM-as-judge evaluation.

This doc is the design of record. The original brief (the project `CLAUDE.md`)
is the source spec; this doc records the concrete decisions made before build
and the enhancements layered on top.

## 2. Locked decisions

| Decision | Choice | Notes |
|---|---|---|
| LLM provider | **OpenAI** | Key read from `OPENAI_API_KEY` env, never hardcoded. Must be exported before Phase 2 runs. |
| Target app | **Parabank, local Docker** | `parasoft/parabank` on `:8080`. Stable + repeatable. Public host is fallback only. |
| Repo location | `~/Desktop/llm-ai-projects/agentic-qa` | |
| Scope | **All phases (0–8)**, pause only on failure | |
| Python | 3.13 (spec floor 3.11+) | managed with `uv` |
| Page state | **Accessibility tree**, not raw HTML | compact, token-cheap, is what the agent reasons over |
| Judge output | **Pydantic `Verdict`** | typed, storable, regression-testable |
| Model split | cheaper model for explorer, stronger for judge | configurable in `config.py` |

## 3. Enhancements beyond the base spec

These earn their place against the pitch ("autonomous exploration, **self-healing
intent**, RAG-grounded evaluator"); nothing speculative is added.

1. **Self-healing explorer loop.** When a tool action fails (element missing,
   timeout, navigation error), the explorer does NOT crash. It records the
   failure, re-snapshots the page, and re-plans the next step. A flow ends on
   goal-completion, step budget, or N consecutive unrecoverable failures. This
   is the literal "self-healing intent" in the pitch — implemented, not named.
2. **Thin provider abstraction (`llm.py`).** One `chat()` / `chat_structured()`
   interface over the OpenAI SDK. Lets the judge be unit-tested offline with a
   stubbed client and keeps the provider swappable.
3. **Typed contracts everywhere.** Pydantic models: `Action`, `StepRecord`,
   `ObservationBundle`, `Verdict`. Bundles serialize to JSON under `runs/`.
4. **Offline-replayable judge.** `judge(bundle)` takes a bundle object/file, so
   judge tests run with no browser and (with a stubbed llm) no network. Ship one
   known-good and one known-broken fixture bundle for regression tests.
5. **Token/cost accounting** surfaced in the report (per-flow + total).

YAGNI guards: no plugin system, no multi-provider router, no async job queue,
no web UI. Phases 6–8 stay minimal (SQLite not Postgres unless Phase 7 needs
pgvector; planted-bug app is a ~5-route Flask prop, not a product).

## 4. Architecture

```
            +-------------------+
            |  Parabank (:8080) |   system under test
            +-------------------+
              ^               |
       observe|               |drive (Playwright tools)
              |               v
  +---------------------------------------------------+
  |  LangGraph orchestrator (shared QAState)          |
  |   explorer_node --bundle--> judge_node --> report_node
  |        ^                                        |  |
  |        +-------------- next flow ---------------+  |
  +---------------------------------------------------+
```

### Components (one clear purpose each)

- `config.py` — target URL, model names, run settings, step budgets, paths.
- `llm.py` — provider abstraction (`chat`, `chat_structured`), token accounting.
- `tools.py` — Playwright actions as callables: `navigate`, `click`, `fill`,
  `get_page_state` (a11y snapshot), `screenshot`, `get_console_errors`,
  `get_network_failures`. Each takes a `Page`, returns a typed result, and
  raises a typed `ToolError` on failure (fuel for self-healing).
- `explorer.py` — explorer agent + the observe→decide→act→record loop and the
  self-healing policy. Produces an `ObservationBundle`.
- `judge.py` — `Verdict` schema + `judge(bundle) -> Verdict`. (Phase 7 adds a
  RAG-grounded variant `judge_grounded`.)
- `graph.py` — LangGraph wiring + `QAState` shared state.
- `report.py` — render verdicts + bundles to markdown/HTML.
- `history.py` (Phase 6) — SQLite run log + a couple of real aggregate queries.
- `rag.py` (Phase 7) — pgvector index of expected-behavior notes + retrieval.
- `cli.py` — entry point: `agentic-qa run --flows transfer,billpay`.

### Data flow

flows list → for each flow: explorer loop builds `ObservationBundle` (saved to
`runs/<ts>/<flow>.json` + screenshots) → judge reads bundle → `Verdict` →
report aggregates verdicts → markdown/HTML artifact in `runs/<ts>/report.md`.

## 5. Error handling

- Tools raise `ToolError(action, detail)`; explorer catches, records, re-plans.
- LLM calls: bounded retries with backoff; on persistent failure the step is
  recorded as `status="llm_error"` and the flow ends gracefully.
- Judge structured-output parse failure → one reformat retry → else
  `status="uncertain"` with the raw text in `reasoning`.
- Missing `OPENAI_API_KEY` → fail fast at startup with a clear message.
- Parabank unreachable → fail fast with the URL and a "is Docker up?" hint.

## 6. Testing

- `tests/test_tools.py` — each tool against a tiny local static page (no LLM).
- `tests/test_judge.py` — stubbed llm + 2 fixture bundles (good / broken).
- `tests/test_e2e.py` — graph runs one flow end-to-end (marked `slow`, needs
  Parabank + key; skipped in unit CI).
- TDD: write the test for each unit before its implementation.

## 7. Build order (matches spec phases)

0 Skeleton → 1 Tools → 2 Explorer (plain Python) → 3 Judge → 4 LangGraph →
5 pytest suite + CLI + report → 6 SQLite history → 7 RAG-grounded judge
(pgvector) → 8 planted-bug Flask app + recorded catch.

Each phase runs and is reviewable on its own. LangGraph not before Phase 4;
pgvector not before Phase 7.

## 8. Definition of done

One repo, one command, points at Parabank, emits a report of flows tested with
structured verdicts. README with architecture + run instructions + the
planted-bug catch log. Supports the pitch: "an agent swarm that explores a web
app, finds broken flows, and judges its own results, with a RAG-grounded
evaluator."
