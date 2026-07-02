"""Offline test of the LangGraph orchestration wiring.

Navigation is stubbed and the LLM is faked, so this validates the graph's
control flow (loop over flows, aligned bundles/verdicts, report emission)
without Parabank or an API key.
"""

from __future__ import annotations

from agentic_qa import tools
from agentic_qa.graph import run_qa
from agentic_qa.judge import Verdict
from agentic_qa.schema import Action, ExplorerDecision, FlowSpec
from tests.conftest import FakeLLM

PAGE_HTML = "<!doctype html><html><head><title>Stub</title></head><body><p>ok</p></body></html>"


async def test_graph_loops_flows_and_writes_report(page, tmp_path, monkeypatch):
    await page.set_content(PAGE_HTML)
    tools.instrument(page)

    # Stub navigation so no server is needed; keep the current set_content page.
    async def fake_navigate(pg, url):
        return pg.url

    monkeypatch.setattr(tools, "navigate", fake_navigate)

    flows = [
        FlowSpec(flow="alpha", goal="do alpha", start_page="a.htm"),
        FlowSpec(flow="beta", goal="do beta", start_page="b.htm"),
    ]

    # Call order: explore(alpha) -> judge(alpha) -> explore(beta) -> judge(beta)
    finish = ExplorerDecision(
        reasoning="nothing to do, finish",
        action=Action(kind="finish", value="completed"),
    )
    v_alpha = Verdict(status="pass", category="functional", severity="low",
                      reasoning="alpha fine", confidence=0.8)
    v_beta = Verdict(status="fail", category="data_error", severity="high",
                     reasoning="beta wrong total", confidence=0.7)
    llm = FakeLLM([finish, v_alpha, finish, v_beta])

    state = await run_qa(
        page=page, llm=llm, flows=flows, run_dir=tmp_path, base_url="http://x",
    )

    assert len(state["bundles"]) == 2
    assert len(state["verdicts"]) == 2
    assert [b.flow for b in state["bundles"]] == ["alpha", "beta"]
    assert [v.status for v in state["verdicts"]] == ["pass", "fail"]

    report = (tmp_path / "report.md").read_text()
    assert "alpha" in report and "beta" in report
    assert "2 — 1 pass, 1 fail" in report
    assert state["report_path"].endswith("report.md")
