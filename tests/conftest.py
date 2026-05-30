"""Shared pytest fixtures.

A fresh browser + page per test keeps the tool tests fully isolated and avoids
event-loop-scope pitfalls with pytest-asyncio. Tests here use in-memory pages
(set_content / data: URLs) so they need neither a server nor an API key.
"""

from __future__ import annotations

from typing import Type, TypeVar

import pytest_asyncio
from playwright.async_api import async_playwright
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class FakeLLM:
    """A scripted stand-in for LLMClient.

    Returns queued Pydantic objects in order, ignoring the prompt. Lets the
    explorer/judge loops be tested deterministically with no network or key.
    """

    def __init__(self, responses: list[BaseModel]) -> None:
        self._responses = list(responses)
        self.received: list[list[dict[str, str]]] = []
        self.calls = 0

    async def chat_structured(
        self, *, messages: list[dict[str, str]], model: str, schema: Type[T]
    ) -> T:
        self.received.append(messages)
        self.calls += 1
        if not self._responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return self._responses.pop(0)  # type: ignore[return-value]


@pytest_asyncio.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        pg = await browser.new_page()
        try:
            yield pg
        finally:
            await browser.close()
