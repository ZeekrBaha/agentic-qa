"""Unit tests for the Playwright tool layer (no server, no LLM)."""

from __future__ import annotations

import pytest

from agentic_qa import config, tools
from agentic_qa.tools import ToolError

FORM_HTML = """
<!doctype html><html><head><title>Test Form</title></head><body>
  <h1>Test Form</h1>
  <a href="#next" id="go">Go Next</a>
  <label for="amt">Amount</label>
  <input id="amt" name="amount" type="text">
  <button id="submit" onclick="document.title='clicked!'">Submit</button>
</body></html>
"""


async def test_get_page_state_lists_interactive_with_selectors(page):
    await page.set_content(FORM_HTML)
    state = await tools.get_page_state(page)

    assert state["title"] == "Test Form"
    assert "Test Form" in state["headings"]
    names = {e["name"] for e in state["interactive"]}
    assert "Go Next" in names
    assert "Submit" in names
    # Every interactive element carries a ready-to-use selector.
    for e in state["interactive"]:
        assert e["selector"].startswith('[data-aqa-ref="')
    roles = {e["role"] for e in state["interactive"]}
    assert {"link", "textbox", "button"} <= roles


async def test_fill_then_click_via_returned_selectors(page):
    await page.set_content(FORM_HTML)
    state = await tools.get_page_state(page)
    by_name = {e["name"]: e for e in state["interactive"]}

    amount = by_name["Amount"]  # accessible name comes from <label>
    await tools.fill(page, amount["selector"], "123.45")
    assert await page.locator(amount["selector"]).input_value() == "123.45"

    await tools.click(page, by_name["Submit"]["selector"])
    assert await page.title() == "clicked!"


async def test_navigate_returns_final_url(page):
    final = await tools.navigate(page, "data:text/html,<h1>Hello</h1>")
    assert final.startswith("data:text/html")


async def test_navigate_bad_host_raises_toolerror(page, monkeypatch):
    monkeypatch.setattr(config.RUN, "action_timeout_ms", 1500)
    with pytest.raises(ToolError) as exc:
        await tools.navigate(page, "http://127.0.0.1:9/nope")
    assert exc.value.action == "navigate"


async def test_click_missing_selector_raises_toolerror(page, monkeypatch):
    monkeypatch.setattr(config.RUN, "action_timeout_ms", 1000)
    await page.set_content("<body><p>nothing here</p></body>")
    with pytest.raises(ToolError) as exc:
        await tools.click(page, '[data-aqa-ref="e999"]')
    assert exc.value.action == "click"


async def test_console_errors_captured_after_instrument(page):
    tools.instrument(page)
    await page.set_content(
        "<body><script>console.error('boom');"
        "setTimeout(() => { throw new Error('explode'); }, 0);</script></body>"
    )
    # Give the queued uncaught exception a tick to surface.
    await page.wait_for_timeout(100)
    errors = await tools.get_console_errors(page)
    assert any("boom" in e for e in errors)
    assert any("explode" in e for e in errors)


async def test_network_failure_captured(page):
    tools.instrument(page)
    async with page.expect_event("requestfailed", timeout=5000):
        await page.set_content('<body><img src="http://127.0.0.1:9/missing.png"></body>')
    failures = await tools.get_network_failures(page)
    assert any(f["type"] == "request_failed" for f in failures)
    assert any("127.0.0.1:9" in f.get("url", "") for f in failures)
