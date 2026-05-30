"""Offline tests for the explorer loop: self-healing and termination.

No API key, no Parabank. A scripted FakeLLM drives a real Chromium page loaded
from set_content, so the full observe->decide->act->record cycle and the
self-healing policy are validated deterministically.
"""

from __future__ import annotations

import pytest

from agentic_qa import config, tools
from agentic_qa.config import RunSettings
from agentic_qa.explorer import explore
from agentic_qa.schema import Action, ExplorerDecision
from tests.conftest import FakeLLM

# input#amt is tagged e0, the submit button e1 (document order).
FORM_HTML = """
<!doctype html><html><body>
  <label for="amt">Amount</label>
  <input id="amt" name="amount" type="text">
  <button onclick="document.title='submitted!'">Submit</button>
</body></html>
"""


@pytest.fixture(autouse=True)
def fast_timeout(monkeypatch):
    # Keep tool failures fast (default action timeout is 8s).
    monkeypatch.setattr(config.RUN, "action_timeout_ms", 800)


async def test_explorer_self_heals_after_failed_action(page, tmp_path):
    await page.set_content(FORM_HTML)
    tools.instrument(page)

    # Step 1 targets a bogus ref (fails); the agent re-plans to the real field.
    llm = FakeLLM([
        ExplorerDecision(reasoning="try filling amount",
                         action=Action(kind="fill", selector='[data-aqa-ref="e999"]', value="100")),
        ExplorerDecision(reasoning="that selector was wrong, use the real one",
                         action=Action(kind="fill", selector='[data-aqa-ref="e0"]', value="100")),
        ExplorerDecision(reasoning="submit the form",
                         action=Action(kind="click", selector='[data-aqa-ref="e1"]')),
        ExplorerDecision(reasoning="done",
                         action=Action(kind="finish", value="Filled amount 100 and submitted successfully.")),
    ])

    bundle = await explore(
        page, flow="demo", goal="fill the amount and submit",
        llm=llm, settings=RunSettings(max_steps=10), run_dir=tmp_path,
    )

    statuses = [s.status for s in bundle.steps]
    assert statuses == ["tool_error", "ok", "ok", "ok"]
    assert bundle.finished_reason == "agent_finished"
    assert "submitted" in bundle.finish_summary.lower()
    # The recovery actually worked against the real DOM:
    assert await page.locator('[data-aqa-ref="e0"]').input_value() == "100"
    assert await page.title() == "submitted!"
    # Bundle persisted for offline judging.
    assert (tmp_path / "demo.json").exists()
    assert bundle.final_page_state["title"] == "submitted!"


async def test_explorer_stops_after_max_consecutive_failures(page):
    await page.set_content(FORM_HTML)
    tools.instrument(page)

    llm = FakeLLM([
        ExplorerDecision(reasoning="bad", action=Action(kind="click", selector='[data-aqa-ref="x"]'))
        for _ in range(5)
    ])

    bundle = await explore(
        page, flow="doomed", goal="click a nonexistent thing",
        llm=llm, settings=RunSettings(max_steps=10, max_consecutive_failures=3),
    )

    assert bundle.finished_reason == "max_failures"
    assert len(bundle.steps) == 3
    assert all(s.status == "tool_error" for s in bundle.steps)
