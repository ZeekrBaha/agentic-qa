# Repo Engineering Re-Review — agentic-qa

Date: 2026-07-01 19:52 (local) · Reviewer: Claude Code (repo-engineering-review skill)
Target: `/Users/baha/Desktop/llm-ai-projects/agentic-qa` (git: ZeekrBaha/agentic-qa, main @ `72771f5`, clean tree, in sync with origin)
Prior review: `docs/reviews/2026-07-01-1935-repo-engineering-review.md`

**About**
`agentic-qa` — Python 3.13 multi-agent QA system: Explorer agent (gpt-4o + Playwright) autonomously walks web-app flows against Parabank, Judge agent scores each with a structured `Verdict`, LangGraph orchestration, optional RAG-grounded judging, SQLite run history, markdown+HTML reports, planted-bug Flask demo.

**Verdict**
**Ship.** All six improvement items from the 19:35 review were fixed in commit `72771f5` ("Address repo engineering review findings"). Re-run of every gate on the live tree: **31/31 unit tests pass, ruff clean, mypy clean, pip-audit clean, lockfile committed, CI enforces all of it.** Only remaining defect is a stale "30 unit tests" count in README/VALIDATION docs (polish).

---

## What Changed Since the Prior Review (verified against commit 72771f5)

| Prior finding | Status now | Evidence |
| --- | --- | --- |
| No lint/type gates (7 ruff + 5 mypy findings) | **Fixed** | `[tool.ruff]`/`[tool.mypy]` in `pyproject.toml`; `uvx ruff check src tests` → "All checks passed!"; `mypy src/agentic_qa` → "Success: no issues found in 18 source files". Commit note: 2 additional mypy findings surfaced against the real dependency set were also fixed. |
| No committed lockfile | **Fixed** | `uv.lock` tracked; CI installs via `uv sync --all-extras --locked`. |
| `report.py:141` console errors rendered as Python list repr | **Fixed, test-first** | `report.py` joins errors; `tests/test_report.py` +18 lines; suite grew 30 → 31. |
| No pip-audit in CI | **Fixed** | "Dependency audit" step in `.github/workflows/ci.yml`. |
| Dead code `skeleton.py` / `run_explorer.py` | **Fixed** | Both files removed (-91 lines); `src/agentic_qa/` listing confirms. |
| Confusing 16-error failure when Chromium missing | **Fixed** | `tests/conftest.py:48-51` skips with "Chromium not installed — run `playwright install chromium`". |

## What Was Done Well (carried forward, still true on live tree)

- One-way dependency graph (schema → tools/config → explorer/judge → graph → cli), no cycles — confirmed via import scan in prior review; no structural changes since beyond file deletions.
- Full DI (`SupportsStructured` protocol, `FakeLLM`), offline deterministic suite, e2e behind `slow` marker.
- TDD discipline: the report fix itself landed test-first per commit message and diff (test file grew with the fix).
- Honest validation docs (`docs/VALIDATION.md`), comprehensive README with screenshots, phased commit history.
- CI now a real quality gate: locked sync → ruff → mypy → pip-audit → chromium → pytest.

## What Was Done Badly (remaining)

- **Stale test counts (polish, doc drift):** `README.md:201`, `README.md:210`, `docs/VALIDATION.md:3` still say "30 unit tests"; the suite is now 31 after the test-first report fix.
- Nothing else found. Prior architecture note stands as an optional consolidation: `run_demo.py` still bypasses the LangGraph orchestrator (separate showcase path) — acceptable, documented behavior.

## README

Exists, comprehensive (mental model, architecture diagram, rationale, quickstart, keys, repo map, testing, validation, phases, stack, limitations), screenshots embedded. Only defect: the stale "30 tests" counts above.

## TDD / Tests

- `uv run pytest -q` → **31 passed, 2 deselected, 5.92s**.
- New evidence of TDD discipline: report rendering fix shipped with its regression test in the same commit, described as test-first.

## Lint / Type / CI

- `uvx ruff check src tests` → **All checks passed!** (now configured: line-length 120, E/F/I selects)
- `uvx mypy src/agentic_qa --ignore-missing-imports` → **Success, 18 source files**.
- CI: lint + type + audit + tests, all on locked dependencies. Gate posture is now solid for a project this size.

## Security / Vulnerabilities

- `pip-audit` → **No known vulnerabilities found** (re-run on live venv).
- Lockfile now pins the dependency set; CI audits it every push.
- Standing notes unchanged: demo Flask app's `"demo-not-secret"` key is intentional and labeled; prompt-injection surface limited to the configured target URL.

## How To Improve

1. Update the three stale "30 unit tests" references to 31 (`README.md:201`, `README.md:210`, `docs/VALIDATION.md:3`) — or drop the hard-coded count in favor of "the unit suite" to end this class of drift.

## How To Enhance (unchanged from prior review)

- Anthropic backend behind the existing `SupportsStructured` protocol.
- Vision-grounded judge (final screenshot) to attack the documented Bill Pay false positives.
- Route the demo through `build_graph()` for a single orchestration path.
- Parallel flows via browser contexts; per-run cost budget guard; broader flow coverage.

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Unit tests | `uv run pytest -q` | 31 passed, 2 deselected, 5.92s |
| Lint | `uvx ruff check src tests` | All checks passed |
| Types | `uvx mypy src/agentic_qa --ignore-missing-imports` | Success, 18 files |
| Dependency audit | `uv run --with pip-audit pip-audit` | No known vulnerabilities |
| Git state | `git status -sb` | main in sync with origin/main, clean tree |
| Fix commit | `git show --stat 72771f5` | All six prior findings addressed |

Incident during review: a cleanup step deleted the now-tracked `uv.lock`; restored immediately via `git checkout -- uv.lock`, tree verified clean. Skipped: `pytest -m slow` (needs live Parabank + OPENAI_API_KEY spend).

## Saved Observations

`docs/reviews/2026-07-01-1952-repo-engineering-review.md`
