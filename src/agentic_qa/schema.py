"""Typed contracts shared across the system.

These Pydantic models are the interfaces between components: the explorer emits
an ``ObservationBundle``, the judge consumes it and emits a ``Verdict``. Keeping
them typed means every artifact is storable, countable, and regression-testable.
``ExplorerDecision`` doubles as the structured-output schema the explorer LLM
must conform to.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ActionKind = Literal["navigate", "click", "fill", "finish"]


class Action(BaseModel):
    """A single action the explorer wants to take."""

    kind: ActionKind
    selector: Optional[str] = Field(
        default=None, description="CSS selector for click/fill (use a provided ref)."
    )
    value: Optional[str] = Field(
        default=None, description="Text to type for 'fill'; final summary for 'finish'."
    )
    url: Optional[str] = Field(
        default=None, description="Destination for 'navigate'."
    )


class ExplorerDecision(BaseModel):
    """What the explorer LLM returns each step: why, then what to do."""

    reasoning: str = Field(description="One sentence: why this action advances the goal.")
    action: Action


class StepRecord(BaseModel):
    """The record of one observe->decide->act cycle."""

    step: int
    reasoning: str
    action: Action
    result: str
    status: Literal["ok", "tool_error", "llm_error"]
    page_url: str


class ObservationBundle(BaseModel):
    """Everything the judge needs to score one completed flow."""

    flow: str
    goal: str
    start_url: str
    steps: list[StepRecord] = Field(default_factory=list)
    final_page_state: dict[str, Any] = Field(default_factory=dict)
    console_errors: list[str] = Field(default_factory=list)
    network_failures: list[dict[str, Any]] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)
    finished_reason: Literal["agent_finished", "max_steps", "max_failures"] = "max_steps"
    finish_summary: str = ""
