"""Phase 0 skeleton: prove browser automation against Parabank.

No LLM. Opens a browser, logs the test user in (registering if needed), lands
on the Accounts Overview, and saves a screenshot to runs/. Run with:

    python -m agentic_qa.skeleton
"""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright

from . import config
from .auth import ensure_logged_in


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=config.RUN.headless)
        page = await browser.new_page()
        page.set_default_timeout(config.RUN.action_timeout_ms)

        await ensure_logged_in(page)

        # Land on the accounts overview and confirm it actually rendered.
        await page.goto(config.url("overview.htm"))
        await page.wait_for_load_state("networkidle")
        heading = await page.locator("h1.title").first.inner_text()
        rows = await page.locator("#accountTable tbody tr").count()

        out = config.runs_dir() / "phase0_overview.png"
        await page.screenshot(path=str(out), full_page=True)

        print(f"Logged in. Page heading: {heading!r}")
        print(f"Accounts table rows: {rows}")
        print(f"Screenshot saved: {out}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
