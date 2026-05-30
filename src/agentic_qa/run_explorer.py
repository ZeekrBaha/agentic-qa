"""Phase 2 live runner: explore a single Parabank flow with a real LLM.

Requires OPENAI_API_KEY and a reachable Parabank. Logs in, instruments the page,
runs one flow, and writes the observation bundle + screenshot to runs/<ts>/.

    python -m agentic_qa.run_explorer "test the funds-transfer flow"
"""

from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

from . import config, tools
from .auth import ensure_logged_in
from .explorer import explore, new_run_dir
from .llm import LLMClient


async def main(goal: str, flow: str = "transfer") -> None:
    llm = LLMClient()  # fails fast here if OPENAI_API_KEY is missing
    run_dir = new_run_dir()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=config.RUN.headless)
        page = await browser.new_page()
        page.set_default_timeout(config.RUN.action_timeout_ms)
        tools.instrument(page)  # attach listeners before any navigation

        await ensure_logged_in(page)
        await page.goto(config.url("overview.htm"))

        bundle = await explore(page, flow=flow, goal=goal, llm=llm, run_dir=run_dir)
        await browser.close()

    print(f"\nFlow '{flow}' finished: {bundle.finished_reason}")
    print(f"Steps: {len(bundle.steps)} | console errors: {len(bundle.console_errors)} "
          f"| network failures: {len(bundle.network_failures)}")
    print(f"Summary: {bundle.finish_summary}")
    print(f"Tokens: {llm.usage}")
    print(f"Bundle: {run_dir / (flow + '.json')}")


if __name__ == "__main__":
    goal_arg = sys.argv[1] if len(sys.argv) > 1 else "test the funds-transfer flow"
    asyncio.run(main(goal_arg))
