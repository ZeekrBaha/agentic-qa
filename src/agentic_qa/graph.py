"""LangGraph orchestrator: explorer -> judge -> (loop) -> report.

This is where "multi-agent" becomes real. ``QAState`` holds only data; the
browser page and LLM client are injected via a factory closure because they are
runtime handles, not serializable state.

Graph shape::

    START -> explorer -> judge --(more flows?)--> explorer
                              \\--(done)--> report -> END
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from playwright.async_api import Page

from . import config, tools
from .explorer import SupportsStructured, explore
from .judge import Verdict, judge
from .report import render_markdown
from .schema import FlowSpec, ObservationBundle

# Optional hook: given a flow, return documented expected-behavior text to
# ground the judge's verdict (used by the Phase 7 RAG judge).
JudgeContextFn = Callable[[FlowSpec], str]


class QAState(TypedDict):
    flows: list[FlowSpec]
    current_index: int
    bundles: Annotated[list[ObservationBundle], operator.add]
    verdicts: Annotated[list[Verdict], operator.add]
    report_path: str


def build_graph(
    *,
    page: Page,
    llm: SupportsStructured,
    run_dir: Path,
    base_url: str = config.BASE_URL,
    explorer_model: str = config.EXPLORER_MODEL,
    judge_model: str = config.JUDGE_MODEL,
    settings: config.RunSettings | None = None,
    judge_context: JudgeContextFn | None = None,
):
    """Compile a QA graph bound to a specific page + LLM."""

    async def explorer_node(state: QAState) -> dict[str, Any]:
        spec = state["flows"][state["current_index"]]
        tools.reset_capture(page)  # per-flow error isolation
        await tools.navigate(page, config.url(spec.start_page))
        bundle = await explore(
            page,
            flow=spec.flow,
            goal=spec.goal,
            llm=llm,
            model=explorer_model,
            settings=settings,
            run_dir=run_dir,
        )
        return {"bundles": [bundle]}

    async def judge_node(state: QAState) -> dict[str, Any]:
        spec = state["flows"][state["current_index"]]
        bundle = state["bundles"][-1]
        context = judge_context(spec) if judge_context else ""
        verdict = await judge(
            bundle, llm=llm, model=judge_model, extra_context=context
        )
        return {"verdicts": [verdict], "current_index": state["current_index"] + 1}

    def route_after_judge(state: QAState) -> str:
        return "explorer" if state["current_index"] < len(state["flows"]) else "report"

    async def report_node(state: QAState) -> dict[str, Any]:
        path = render_markdown(
            bundles=state["bundles"],
            verdicts=state["verdicts"],
            run_dir=run_dir,
            base_url=base_url,
            explorer_model=explorer_model,
            judge_model=judge_model,
            usage=getattr(llm, "usage", None),
            timestamp=run_dir.name,
        )
        return {"report_path": str(path)}

    g = StateGraph(QAState)
    g.add_node("explorer", explorer_node)
    g.add_node("judge", judge_node)
    g.add_node("report", report_node)
    g.add_edge(START, "explorer")
    g.add_edge("explorer", "judge")
    g.add_conditional_edges(
        "judge", route_after_judge, {"explorer": "explorer", "report": "report"}
    )
    g.add_edge("report", END)
    return g.compile()


async def run_qa(
    *,
    page: Page,
    llm: SupportsStructured,
    flows: list[FlowSpec],
    run_dir: Path,
    base_url: str = config.BASE_URL,
    explorer_model: str = config.EXPLORER_MODEL,
    judge_model: str = config.JUDGE_MODEL,
    settings: config.RunSettings | None = None,
    judge_context: JudgeContextFn | None = None,
) -> QAState:
    """Run the full graph over ``flows`` and return the final state."""
    graph = build_graph(
        page=page,
        llm=llm,
        run_dir=run_dir,
        base_url=base_url,
        explorer_model=explorer_model,
        judge_model=judge_model,
        settings=settings,
        judge_context=judge_context,
    )
    initial: QAState = {
        "flows": flows,
        "current_index": 0,
        "bundles": [],
        "verdicts": [],
        "report_path": "",
    }
    # Each flow uses 2 supersteps; give headroom for the report + loop.
    result = await graph.ainvoke(initial, {"recursion_limit": 4 * len(flows) + 5})
    return result  # type: ignore[return-value]
