"""Explorer agent: observe -> decide -> act -> record, with self-healing.

Given a goal, the explorer snapshots the page (compact a11y view), asks the LLM
for one next action, executes it through the tool layer, and records the result.
A failed action is not fatal: the failure is fed back into the next prompt so
the model can re-plan (the "self-healing intent" the project is about). A flow
ends when the agent calls ``finish``, the step budget runs out, or too many
consecutive actions fail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, Type, TypeVar

from playwright.async_api import Page
from pydantic import BaseModel

from . import config, tools
from .config import RunSettings
from .schema import Action, ExplorerDecision, ObservationBundle, StepRecord
from .tools import ToolError

T = TypeVar("T", bound=BaseModel)


class SupportsStructured(Protocol):
    """Minimal LLM interface the explorer depends on (real client or a fake)."""

    async def chat_structured(
        self, *, messages: list[dict[str, str]], model: str, schema: Type[T]
    ) -> T: ...


SYSTEM_PROMPT = """\
You are an autonomous QA explorer testing a banking web application. Your job is
to accomplish a given goal by interacting with the page, the way a careful human
tester would, and to notice when something is broken.

Each turn you are given the goal, a compact view of the current page (its title,
headings, visible text, and a list of interactive elements), and a short history
of your recent actions and their results.

Rules:
- Choose exactly ONE next action per turn.
- To click or fill, use the EXACT `selector` string from the interactive
  elements list. Never invent selectors.
- Fill required fields before clicking submit/continue buttons.
- For a dropdown (role combobox), use kind "select" with its selector and put
  EXACTLY one of its listed option values (the quoted value before each label)
  in "value". Do not invent option values.
- Put only the plain value in "value" — no extra characters, brackets, or quotes.
- If an action failed last turn (status tool_error), do not repeat it blindly:
  re-read the current page and try a different element or approach.
- Call action.kind = "finish" when the goal is achieved OR you are confident it
  cannot be achieved. Put a one-paragraph summary of what happened, what the
  final state was, and anything that looked wrong, in action.value.
- Be efficient: do not wander once the goal is done.
"""


def _page_state_for_prompt(state: dict[str, Any]) -> str:
    lines = [
        f"URL: {state.get('url')}",
        f"Title: {state.get('title')}",
    ]
    if state.get("headings"):
        lines.append("Headings: " + " | ".join(state["headings"]))
    lines.append("Interactive elements:")
    for e in state.get("interactive", []):
        val = f" value={e['value']!r}" if e.get("value") else ""
        opts = ""
        if e.get("options"):
            shown = ", ".join(f"{o['value']!r}({o['label']})" for o in e["options"][:12])
            opts = f" options=[{shown}]"
        lines.append(
            f"  - selector={e['selector']} role={e['role']} name={e['name']!r}{val}{opts}"
        )
    text = state.get("text", "")
    if text:
        lines.append(f"Visible text (truncated): {text[:800]}")
    return "\n".join(lines)


def _history_for_prompt(steps: list[StepRecord], last_n: int = 6) -> str:
    if not steps:
        return "(no actions yet)"
    recent = steps[-last_n:]
    out = []
    for s in recent:
        a = s.action
        desc: str = a.kind
        if a.selector:
            desc += f" {a.selector}"
        if a.value and a.kind in ("fill", "select"):
            # Bound the echoed value: a malformed/degenerate value must not feed
            # back into the next prompt and amplify into runaway repetition.
            desc += f" = {a.value[:40]!r}"
        if a.url:
            desc += f" {a.url}"
        out.append(f"step {s.step}: {desc} -> [{s.status}] {s.result[:120]}")
    return "\n".join(out)


async def _execute(page: Page, action: Action) -> str:
    """Dispatch one action to the tool layer. Raises ToolError on failure."""
    if action.kind == "navigate":
        target = action.url or ""
        if not target.startswith("http"):
            target = config.url(target)
        return await tools.navigate(page, target)
    if action.kind == "click":
        if not action.selector:
            raise ToolError("click", "no selector provided")
        return await tools.click(page, action.selector)
    if action.kind == "fill":
        if not action.selector:
            raise ToolError("fill", "no selector provided")
        return await tools.fill(page, action.selector, tools.clean_value(action.value))
    if action.kind == "select":
        if not action.selector:
            raise ToolError("select", "no selector provided")
        return await tools.select_option(page, action.selector, action.value or "")
    raise ToolError(action.kind, "unsupported action")


async def explore(
    page: Page,
    *,
    flow: str,
    goal: str,
    llm: SupportsStructured,
    model: str = config.EXPLORER_MODEL,
    settings: RunSettings | None = None,
    run_dir: Path | None = None,
) -> ObservationBundle:
    """Drive one flow to completion and return its observation bundle.

    The page should already be instrumented (``tools.instrument``) and positioned
    at a sensible starting point (e.g. logged in on the overview).
    """
    settings = settings or config.RUN
    start_url = page.url
    steps: list[StepRecord] = []
    screenshots: list[str] = []
    consecutive_failures = 0
    finished_reason: str = "max_steps"
    finish_summary = ""

    for step_no in range(1, settings.max_steps + 1):
        state = await tools.get_page_state(page)
        user_prompt = (
            f"GOAL: {goal}\n\n"
            f"CURRENT PAGE:\n{_page_state_for_prompt(state)}\n\n"
            f"RECENT ACTIONS:\n{_history_for_prompt(steps)}\n\n"
            f"What is your next action?"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        try:
            decision = await llm.chat_structured(
                messages=messages, model=model, schema=ExplorerDecision
            )
        except Exception as e:  # noqa: BLE001 - record any LLM failure and stop
            steps.append(
                StepRecord(
                    step=step_no,
                    reasoning="(llm error)",
                    action=Action(kind="finish"),
                    result=f"LLM error: {e}",
                    status="llm_error",
                    page_url=page.url,
                )
            )
            finished_reason = "max_failures"
            break

        action = decision.action

        if action.kind == "finish":
            finish_summary = action.value or decision.reasoning
            finished_reason = "agent_finished"
            steps.append(
                StepRecord(
                    step=step_no,
                    reasoning=decision.reasoning,
                    action=action,
                    result="agent declared finish",
                    status="ok",
                    page_url=page.url,
                )
            )
            break

        status: Literal["ok", "tool_error"]
        try:
            result = await _execute(page, action)
            status = "ok"
            consecutive_failures = 0
        except ToolError as e:
            result = str(e)
            status = "tool_error"
            consecutive_failures += 1

        steps.append(
            StepRecord(
                step=step_no,
                reasoning=decision.reasoning,
                action=action,
                result=result,
                status=status,
                page_url=page.url,
            )
        )

        if consecutive_failures >= settings.max_consecutive_failures:
            finished_reason = "max_failures"
            break

    # Capture the final state once the loop ends.
    final_state = await tools.get_page_state(page)
    console_errors = await tools.get_console_errors(page)
    network_failures = await tools.get_network_failures(page)

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        shot = run_dir / f"{flow}_final.png"
        try:
            await tools.screenshot(page, str(shot))
            screenshots.append(str(shot))
        except ToolError:
            pass

    bundle = ObservationBundle(
        flow=flow,
        goal=goal,
        start_url=start_url,
        steps=steps,
        final_page_state=final_state,
        console_errors=console_errors,
        network_failures=network_failures,
        screenshots=screenshots,
        finished_reason=finished_reason,  # type: ignore[arg-type]
        finish_summary=finish_summary,
    )

    if run_dir is not None:
        (run_dir / f"{flow}.json").write_text(bundle.model_dump_json(indent=2))

    return bundle


def new_run_dir() -> Path:
    """Create a timestamped run directory under runs/."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    d = config.runs_dir() / ts
    d.mkdir(parents=True, exist_ok=True)
    return d
