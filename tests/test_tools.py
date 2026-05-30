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


SELECT_HTML = (
    "<label for='acct'>From account</label>"
    "<select id='acct'><option value='1001'>1001 — Checking</option>"
    "<option value='1002'>1002 — Savings</option></select>"
)


def test_clean_value_strips_trailing_json_junk():
    assert tools.clean_value('1001}}}]}') == "1001"
    assert tools.clean_value('100}}]} ') == "100"
    assert tools.clean_value('1002 — Savings}}]}"}}]}') == "1002 — Savings"
    assert tools.clean_value("Acme Utilities") == "Acme Utilities"  # untouched
    assert tools.clean_value("100.00") == "100.00"
    assert tools.clean_value(None) == ""


async def test_get_page_state_exposes_select_options(page):
    await page.set_content(SELECT_HTML)
    state = await tools.get_page_state(page)
    combo = next(e for e in state["interactive"] if e["role"] == "combobox")
    # Name is the label, not the newline-joined option blob.
    assert combo["name"] == "From account"
    assert "\n" not in combo["name"]
    assert combo["options"] == [
        {"value": "1001", "label": "1001 — Checking"},
        {"value": "1002", "label": "1002 — Savings"},
    ]


async def test_select_option_by_label_and_value(page):
    await page.set_content(SELECT_HTML)
    await tools.select_option(page, "#acct", "1002 — Savings")  # by label
    assert await page.locator("#acct").input_value() == "1002"
    await tools.select_option(page, "#acct", "1001")  # by value
    assert await page.locator("#acct").input_value() == "1001"


async def test_select_option_tolerates_noisy_value(page):
    """gpt-4o-mini sometimes appends JSON junk to string values; we recover."""
    await page.set_content(SELECT_HTML)
    await tools.select_option(page, "#acct", '1002}}]}"}}]}')
    assert await page.locator("#acct").input_value() == "1002"


async def test_select_option_unknown_fails_fast(page, monkeypatch):
    monkeypatch.setattr(config.RUN, "action_timeout_ms", 8000)
    await page.set_content(SELECT_HTML)
    import time
    start = time.monotonic()
    with pytest.raises(ToolError) as exc:
        await tools.select_option(page, "#acct", "9999 — Nonexistent")
    assert exc.value.action == "select"
    # Must fail fast (no 8s Playwright wait), well under the action timeout.
    assert time.monotonic() - start < 2.0


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


async def test_fill_missing_selector_fails_fast(page, monkeypatch):
    import time
    monkeypatch.setattr(config.RUN, "action_timeout_ms", 8000)
    await page.set_content("<body><p>no inputs</p></body>")
    start = time.monotonic()
    with pytest.raises(ToolError) as exc:
        await tools.fill(page, '[data-aqa-ref="e3"]', "100")
    assert exc.value.action == "fill"
    assert time.monotonic() - start < 2.0  # not the full 8s wait


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
