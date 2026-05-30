"""Judge agent: an independent assessor of a completed flow.

The explorer is biased toward "I made it work"; the judge provides a separate,
skeptical assessment grounded only in the recorded evidence (what the page
ended up showing, console/network errors, and the explorer's own account). It
returns a typed ``Verdict`` so every judgement is storable and countable.

``judge`` takes an ``ObservationBundle`` (live or loaded from disk), so it can be
run and tested entirely offline against recorded flows.
"""

from __future__ import annotations

import json
from typing import Literal, Protocol, Type, TypeVar

from pydantic import BaseModel, Field

from . import config
from .schema import ObservationBundle

T = TypeVar("T", bound=BaseModel)


class Verdict(BaseModel):
    """The judge's structured assessment of one flow."""

    status: Literal["pass", "fail", "uncertain"]
    category: Literal["functional", "visual", "data_error", "crash"]
    severity: Literal["low", "medium", "high"]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class SupportsStructured(Protocol):
    async def chat_structured(
        self, *, messages: list[dict[str, str]], model: str, schema: Type[T]
    ) -> T: ...


SYSTEM_PROMPT = """\
You are an independent QA judge evaluating whether an automated explorer agent
truly accomplished a banking-app test flow. The explorer is optimistic and tends
to claim success; do not take its summary at face value. Judge only from the
recorded evidence.

Decide:
- status: "pass" if the goal was genuinely achieved with no broken behavior;
  "fail" if something is broken or the goal was not achieved; "uncertain" if the
  evidence is insufficient to tell.
- category: pick the MOST specific one:
    * "crash" — errors, stack traces, HTTP 500, or a dead/blank page.
    * "data_error" — the operation appears to complete but a value is wrong: a
      balance, total, or amount that does not match what the operation should
      have produced (e.g. a transfer that does NOT reduce the source balance).
    * "visual" — layout or content renders incorrectly.
    * "functional" — the action is blocked, errors out, or cannot be completed.
  Prefer "data_error" over "functional" when the action completed but the
  resulting number is incorrect.
- severity: "low" / "medium" / "high" business impact.
- reasoning: cite the specific evidence (a console error, a missing element, an
  unchanged balance, the final page text) that drives your verdict.
- confidence: 0.0–1.0, how sure you are.

A real bug usually shows up as: console errors or uncaught exceptions, failed
network requests / HTTP errors, the explorer giving up (finished_reason
max_failures or max_steps), an error message in the final page text, or the
expected end state not being reached. Absence of these, plus a final page that
matches the goal, supports "pass".
"""


def _bundle_evidence(bundle: ObservationBundle) -> str:
    fps = bundle.final_page_state or {}
    step_lines = [
        f"  step {s.step}: {s.action.kind}"
        + (f" {s.action.selector}" if s.action.selector else "")
        + f" -> [{s.status}] {s.result}"
        for s in bundle.steps
    ]
    return "\n".join(
        [
            f"FLOW: {bundle.flow}",
            f"GOAL: {bundle.goal}",
            f"START URL: {bundle.start_url}",
            f"FINISHED REASON: {bundle.finished_reason}",
            f"EXPLORER SUMMARY: {bundle.finish_summary or '(none)'}",
            "",
            "STEPS:",
            *step_lines,
            "",
            f"CONSOLE ERRORS ({len(bundle.console_errors)}): "
            + (json.dumps(bundle.console_errors) if bundle.console_errors else "none"),
            f"NETWORK FAILURES ({len(bundle.network_failures)}): "
            + (json.dumps(bundle.network_failures) if bundle.network_failures else "none"),
            "",
            "FINAL PAGE:",
            f"  url: {fps.get('url')}",
            f"  title: {fps.get('title')}",
            f"  headings: {fps.get('headings')}",
            f"  text (truncated): {str(fps.get('text', ''))[:1000]}",
        ]
    )


def build_messages(bundle: ObservationBundle, extra_context: str = "") -> list[dict[str, str]]:
    """Assemble the judge prompt. ``extra_context`` is used by the RAG judge."""
    user = f"EVIDENCE:\n{_bundle_evidence(bundle)}\n\n"
    if extra_context:
        user += f"DOCUMENTED EXPECTED BEHAVIOR (ground your verdict in this):\n{extra_context}\n\n"
    user += "Return your verdict."
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


async def judge(
    bundle: ObservationBundle,
    *,
    llm: SupportsStructured,
    model: str = config.JUDGE_MODEL,
    extra_context: str = "",
    max_attempts: int = 2,
) -> Verdict:
    """Score one flow. Falls back to an 'uncertain' verdict if the LLM fails."""
    messages = build_messages(bundle, extra_context)
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            return await llm.chat_structured(messages=messages, model=model, schema=Verdict)
        except Exception as e:  # noqa: BLE001 - degrade gracefully, never crash a run
            last_error = e
    return Verdict(
        status="uncertain",
        category="functional",
        severity="low",
        reasoning=f"Judge could not produce a structured verdict: {last_error}",
        confidence=0.0,
    )
