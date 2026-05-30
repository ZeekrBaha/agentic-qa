# Validation Findings

This system was validated both offline (30 unit tests, scripted fake LLM) and
live (real OpenAI models against a local Parabank container and the planted-bug
demo app). Live validation surfaced several real defects, all root-caused and
fixed; this document records what was found and the resulting conclusions.

## Headline result: the judge discriminates working vs broken

| Scenario | Verdict | Correct? |
| --- | --- | --- |
| Planted-bug demo (transfer never debits source) | `fail / data_error / high` (conf 1.00) | ✅ true positive |
| Real Parabank transfer (working, 2 accounts) | `pass / low` (conf 0.90) | ✅ true negative |

The tool is not a "cry fail" detector: a genuinely working flow passes, a broken
one fails with the correct category and cited reasoning.

## Defects found live and fixed (root-caused)

1. **Dropdown handling.** `<select>` options weren't exposed to the model (the
   accessibility name was the newline-joined option blob), so the model guessed
   option strings and `select_option` waited the full 8s timeout per wrong guess
   → cascaded to `max_failures`. Fix: `get_page_state` exposes `{value,label}`
   options and a clean label; `select_option` matches tolerantly and fails fast.

2. **Structured-output content junk.** gpt-4o-mini sometimes appends junk like
   `100}}]}` inside a string value (strict mode guarantees valid JSON structure,
   not clean content). Fix: `clean_value` strips trailing structural junk at the
   action boundary; option matching tolerates it.

3. **Degeneration feedback loop.** One malformed value, echoed back via the
   action history, amplified into 5,000-char repeated output in *both* models.
   Fix: bound the value/result text shown in the history prompt.

4. **Slow failure on missing elements.** `fill`/`click` waited the full timeout
   when a selector matched nothing (e.g. a field absent after navigation),
   starving the self-healing budget. Fix: fail fast when the locator count is 0.

5. **pgvector dimension mismatch.** A pre-existing `spec_docs` table with a
   different embedding dimension caused insert failures. Fix: `PgVectorStore`
   recreates the table when the stored dimension differs.

6. **Transfer false positive (setup gap).** A freshly-registered Parabank user
   has only one account, so a transfer has no distinct destination and always
   "fails." Fix: `ensure_min_accounts` opens a second account before running, so
   the transfer flow is genuinely testable.

7. **Demo dead-end page.** The demo bank's validation-error page had no form to
   retry. Fix: re-render the form with the error message.

## Known limitations (honest)

- **Explorer model matters.** gpt-4o-mini reliably *flags* bugs but often fails
  to *complete* multi-field flows (~1/3 on funds transfer); gpt-4o completes
  reliably (2/2). The default explorer is therefore `gpt-4o`; set
  `AGENTIC_QA_EXPLORER_MODEL=gpt-4o-mini` to trade reliability for lower cost.
- **Autonomous data entry is imperfect.** On flows with many free-text fields
  (e.g. Bill Pay), the explorer can enter low-quality values (parenthetical
  notes, mismatched account/verify fields), producing soft false-positive
  `fail`s. This is inherent to autonomous exploration; grounding the judge in
  expected behavior (`--rag`) and stronger models reduce it.
- **Confirmation observation.** The explorer occasionally calls `finish` just
  before clearly reading the confirmation page; the judge still scores from the
  captured final state.

## How to reproduce

```bash
export OPENAI_API_KEY=sk-...
# planted-bug catch (controlled, reliable):
python -m agentic_qa.run_demo
# live Parabank discrimination:
agentic-qa run --flows transfer --rag      # -> pass on working Parabank
```
