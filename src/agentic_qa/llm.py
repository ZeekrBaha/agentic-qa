"""Thin provider abstraction over the OpenAI SDK.

One async method, ``chat_structured``, returns a validated Pydantic object using
OpenAI structured outputs. Everything the explorer and judge need goes through
this single interface, which means tests can inject a fake client with the same
shape (see ``tests`` for ``FakeLLM``) and run with no network and no API key.

Token usage accumulates on the instance so the report can show what a run cost.
"""

from __future__ import annotations

from typing import Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from . import config

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised when the model returns no usable structured content."""


class LLMClient:
    """Async OpenAI-backed structured-output client with usage tracking."""

    def __init__(self, api_key: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key or config.get_openai_key())
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    async def chat_structured(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        schema: Type[T],
    ) -> T:
        """Return an instance of ``schema`` parsed from the model's response."""
        resp = await self._client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=schema,
        )
        usage = resp.usage
        if usage is not None:
            self.calls += 1
            self.prompt_tokens += usage.prompt_tokens
            self.completion_tokens += usage.completion_tokens
        parsed = resp.choices[0].message.parsed
        if parsed is None:
            raise LLMError(
                f"model {model} returned no structured content "
                f"(refusal: {resp.choices[0].message.refusal!r})"
            )
        return parsed

    async def embed(
        self, texts: list[str], *, model: str = config.EMBEDDING_MODEL
    ) -> list[list[float]]:
        """Embed a batch of texts (used by the RAG-grounded judge)."""
        resp = await self._client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    @property
    def usage(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
        }
