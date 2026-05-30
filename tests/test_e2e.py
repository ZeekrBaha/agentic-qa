"""End-to-end smoke test: real browser + real Parabank + real LLM.

Marked 'slow' and skipped unless OPENAI_API_KEY is set, so it never runs in the
fast unit CI. Run it explicitly with:

    pytest -m slow tests/test_e2e.py
"""

from __future__ import annotations

import os

import pytest
from playwright.async_api import async_playwright

from agentic_qa import config, flows, tools
from agentic_qa.auth import ensure_logged_in
from agentic_qa.config import RunSettings
from agentic_qa.graph import run_qa
from agentic_qa.llm import LLMClient

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="needs OPENAI_API_KEY for a live run",
    ),
]


async def test_single_flow_end_to_end(tmp_path):
    llm = LLMClient()
    flow_specs = flows.select(["transfer"])
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(config.RUN.action_timeout_ms)
        tools.instrument(page)
        await ensure_logged_in(page)
        state = await run_qa(
            page=page, llm=llm, flows=flow_specs, run_dir=tmp_path,
            settings=RunSettings(max_steps=15),
        )
        await browser.close()

    assert len(state["verdicts"]) == 1
    assert state["verdicts"][0].status in {"pass", "fail", "uncertain"}
    assert (tmp_path / "report.md").exists()
