"""Shared pytest fixtures.

A fresh browser + page per test keeps the tool tests fully isolated and avoids
event-loop-scope pitfalls with pytest-asyncio. Tests here use in-memory pages
(set_content / data: URLs) so they need neither a server nor an API key.
"""

from __future__ import annotations

import pytest_asyncio
from playwright.async_api import async_playwright


@pytest_asyncio.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        pg = await browser.new_page()
        try:
            yield pg
        finally:
            await browser.close()
