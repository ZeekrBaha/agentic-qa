# Repo Engineering Review — agentic-qa

Date: 2026-07-01 19:35 (local) · Reviewer: Claude Code (repo-engineering-review skill)
Target: `/Users/baha/Desktop/llm-ai-projects/agentic-qa` (git: ZeekrBaha/agentic-qa, branch main, clean tree)

**About**
`agentic-qa` — Python 3.13 multi-agent QA system: an Explorer agent (gpt-4o + Playwright) autonomously walks web-app flows against Parabank, a Judge agent scores each flow with a structured `Verdict`, orchestrated by LangGraph, with optional RAG-grounded judging (pgvector / in-memory), SQLite run history, markdown+HTML reports, and a planted-bug Flask demo app. ~1,700 LOC source, ~800 LOC tests.

**Verdict**
**Ship-quality portfolio piece.** 30/30 unit tests pass (7.11s), architecture is cleanly layered with one-way dependencies, README is comprehensive with screenshots, validation is documented honestly (true-positive/true-negative table, root-caused live defects). The gaps are process gates, not correctness: no lint/type tooling configured (ruff finds 7 issues, mypy 5), no committed lockfile, and two small dead-code files.

---

## What Was Done Well

- **Clean one-way dependency graph (confirmed via import scan; serena not used — rg fallback).** `schema.py` is the shared base; `tools.py`/`config.py` sit below the agents; `explorer.py` and `judge.py` are independent of each other; `graph.py` composes them; `cli.py` is the top. No module imports upward, no cycles.
- **Dependency injection throughout.** `SupportsStructured` protocol (`explorer.py`, `judge.py`) lets tests inject a scripted `FakeLLM`; `build_graph()` takes page/llm/settings/judge_context as parameters (`graph.py:build_graph`). The whole unit suite runs offline with no API key.
- **Test posture is real.** 30 unit tests across 9 test files, one per module; recorded good/broken observation bundles (`tests/fixtures/`) let the judge be tested deterministically; e2e isolated behind a `slow` marker excluded by default (`pyproject.toml` addopts).
- **TDD evidence.** Phased commit history (Phase 0–8) with tests landing inside each phase ("Playwright tool layer + unit tests", "explorer agent … offline-validated", "judge agent … offline-replayable"). This is test-alongside development with per-phase validation gates — credible discipline, not retrofitted tests.
- **Honest validation docs.** `docs/VALIDATION.md` + README §Validation report a planted-bug true positive (`fail/data_error/high`, conf 1.00) and a working-flow true negative (`pass/low`, conf 0.90), list six root-caused live defects, and an explicit "Known limitations (honest)" section including model-dependence (gpt-4o-mini can't complete multi-field flows).
- **README is comprehensive**: mental model, architecture diagram, self-healing loop explanation, design rationale, quickstart, key handling, full repo map, testing, validation, build phases, tech stack — plus 4 screenshots in `docs/screenshots/` embedded in the README.
- **Security basics right.** Lazy API-key read with clear failure message (`config.py:get_openai_key`), no hardcoded secrets (scan clean), `.env`/`runs/` gitignored, demo Flask secret explicitly `"demo-not-secret"` (`demo_app/app.py:23`). pip-audit: **no known vulnerabilities**.
- **Thoughtful engineering details.** `clean_value()` in `tools.py` repairs a documented gpt-4o-mini structured-output artifact with the reasoning written down; token accounting on the LLM client surfaces run cost in reports; `ToolError` is treated as fuel for the self-healing loop, not a crash.

## What Was Done Badly

- **No lint or type gates anywhere** (confirmed: no ruff/mypy/black/flake8 in `pyproject.toml` or CI). Probes found real, if minor, issues:
  - `uvx ruff check src tests` → **7 errors, all auto-fixable** (unused imports, e.g. `EXPECTED_BEHAVIOR` in one module).
  - `uvx mypy src/agentic_qa --ignore-missing-imports` → **5 errors in 3 files**.
- **`report.py:141` — `_esc(b.console_errors)` passes a `list[str]` where `str` is expected.** Not a crash (`_esc` calls `str()` first) but console errors render in the HTML report as a Python repr `['boom', 'x']` instead of readable text. Confirmed at runtime. Low severity, cosmetic + type hygiene.
- **`history.py:71` — `int(cur.lastrowid)` where `lastrowid: int | None`.** Pedantic in practice (always int after INSERT), but it is exactly what a mypy gate would force you to make explicit. Low.
- **No committed lockfile.** `pyproject.toml` uses only `>=` bounds and no `uv.lock` is tracked — installs are not reproducible; a future breaking release of langgraph/openai silently changes behavior. Medium.
- **Dead code:** `skeleton.py` (Phase 0 leftover) and `run_explorer.py` (superseded by the Typer CLI) are unreferenced by any code or test — only the README mentions them. Polish.
- **CI is a single unit-test job** (`.github/workflows/ci.yml`): no lint, no types, no dependency audit, single OS. The gates that would have caught the above don't exist in the pipeline.
- **Fresh-clone friction:** without `playwright install chromium`, 16 of 30 tests error with a Playwright launch failure (reproduced locally). A conftest skip-with-message for missing browsers would make the failure self-explaining. Polish.

## README

Exists and comprehensive — covers mental model, architecture (with diagram), design rationale, quickstart, key handling, repo map (every file annotated), testing, validation results, build phases, tech stack, limitations. Screenshots present: `docs/screenshots/{parabank_overview,report_pass,report_fail,demo_bug}.png`, embedded in README. No gaps requiring remediation.

## TDD / Tests

- `uv run pytest -q` → **30 passed, 2 deselected (slow), 7.11s** — after installing Chromium. Before install: 14 passed, 16 errors (environment, not code).
- Coverage spans tools, explorer self-healing loop, judge (fixture replay), graph wiring, report renderers, SQLite history, RAG retrieval, demo app.
- TDD evidence: phased commits each bundling tests + validation ("offline-validated", "offline-replayable"); fixtures recorded for deterministic judge tests; FakeLLM protocol designed for testability from Phase 2. Verdict: genuine test-first/test-alongside discipline, not decoration.

## Lint / Type / CI

- Configured gates: **pytest only** (locally and in CI).
- Missing: ruff (7 findings), mypy (5 findings), pip-audit. Minimal additions for this stack: `ruff check`, `mypy src`, `pip-audit` — all three belong in `ci.yml`.
- CI (`.github/workflows/ci.yml`): uv-based, Python 3.13, installs Chromium with deps, runs unit suite. Works, but is the only gate.

## Security / Vulnerabilities

- **Confirmed clean:** `pip-audit` on the venv → no known vulnerabilities. Secrets scan → no hardcoded credentials. `.env`, `runs/` gitignored.
- **Notes (low risk, by design):** demo Flask app uses a hardcoded `"demo-not-secret"` session key and is a deliberately buggy local-only app — acceptable, clearly labeled. LLM prompt inputs come from pages the agent itself navigates (Parabank/demo app), so prompt-injection surface is limited to the configured target; worth a README caveat if users point `AGENTIC_QA_BASE_URL` at arbitrary sites.
- **Unknowns:** no gitleaks scan run (no findings expected given scan above); no runtime security testing of the demo app (out of scope — it's an intentional bug fixture).

## Architecture Assessment (AI-readiness)

**Good.** Evidence:

- **Coupling direction:** strictly downward. `explorer.py` imports `config/tools/schema`; `judge.py` imports `config/schema`; `graph.py` imports both plus `report`; `history.py`/`report.py` import `judge.Verdict` + `schema` only. No lateral agent-to-agent imports, no upward imports.
- **Sinks vs pipes:** no hidden cascades. `report_node` and `history` writes are explicit, invoked by the graph; nothing triggers downstream side effects invisibly.
- **Side-effect visibility:** `QAState` is a data-only TypedDict; runtime handles (browser page, LLM client) are injected via factory closure and documented as such in `graph.py`'s docstring. Token usage is instance state on the LLM client — visible in the interface.
- **Progressive disclosure:** directory layout mirrors the conceptual architecture one-to-one, and the README repo map annotates every file. An agent can navigate this codebase from the README alone.

One structural judgment call worth noting: `run_demo.py` bypasses the LangGraph orchestrator and calls explore/judge directly — fine for a showcase, but it means two orchestration paths exist. Consolidating the demo onto `build_graph()` would remove the duplication.

## How To Improve (ordered by impact)

1. **Add ruff + mypy config and fix the 12 findings** (7 ruff auto-fixable; the 5 mypy errors include the two real items above). Add both to CI.
2. **Commit `uv.lock`** (adopt `uv sync` in CI) for reproducible installs.
3. **Fix `report.py:141`**: `_esc("; ".join(b.console_errors))`.
4. **Add `pip-audit` step to CI** so the clean dependency state stays enforced.
5. **Delete or archive `skeleton.py` and `run_explorer.py`** (or mark clearly as historical in the repo map).
6. **Self-explaining browser failure:** conftest fixture that skips Playwright tests with "run `playwright install chromium`" when the binary is missing.

## How To Enhance

- **Provider abstraction payoff:** add an Anthropic backend behind the existing `SupportsStructured` protocol — the design already supports it; one class in `llm.py`.
- **Screenshot-grounded judge (vision):** the documented Bill Pay false positives stem from text-only evidence; feeding the final screenshot to the judge targets the known limitation directly.
- **Route the demo through the graph** to have a single orchestration path.
- **Parallel flows** via multiple browser contexts — flows are independent; LangGraph supports fan-out.
- **Per-run cost budget guard** using the existing token accounting (abort or warn past a threshold).
- **Flow coverage growth:** registration, loan request, negative-path flows (bad routing number, overdraft).

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Unit tests | `uv run pytest -q` | 30 passed, 2 deselected, 7.11s (after `playwright install chromium`; before: 16 env errors) |
| Dependency audit | `uv run --with pip-audit pip-audit` | No known vulnerabilities |
| Lint probe | `uvx ruff check src tests` | 7 errors, 7 auto-fixable (not configured in repo) |
| Type probe | `uvx mypy src/agentic_qa --ignore-missing-imports` | 5 errors in 3 files (not configured in repo) |
| Secrets scan | rg for hardcoded keys/passwords | Clean |
| Import graph | rg on `^(from\|import)` in `src/` | One-way, no cycles |
| Runtime check | `_esc(['boom','x'])` | Returns repr string — cosmetic bug confirmed, no crash |

Skipped: `pytest -m slow` (needs live Parabank + OPENAI_API_KEY spend); gitleaks (no indication of need). Side-effect cleanup: a stray `uv.lock` generated by the audit run was removed; tree left clean.
