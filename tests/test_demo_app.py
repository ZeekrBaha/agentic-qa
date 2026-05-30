"""Tests for the Phase 8 planted-bug demo.

1. A Flask-test-client test proves the planted bug exists and is observable
   (offline, no browser, no key).
2. A live integration starts the app in a thread and drives it with a scripted
   explorer (real browser, no key), proving the agent CAPTURES the bug evidence
   in its observation bundle — which is what the judge would then score.
"""

from __future__ import annotations

import threading

import pytest
from werkzeug.serving import make_server

from agentic_qa import config, tools
from agentic_qa.config import RunSettings
from agentic_qa.demo_app.app import app
from agentic_qa.explorer import explore
from agentic_qa.schema import Action, ExplorerDecision
from tests.conftest import FakeLLM


def test_planted_bug_source_balance_not_debited():
    client = app.test_client()
    client.post("/login", data={"username": "demo", "password": "demo"})
    resp = client.post(
        "/transfer", data={"from_acct": "1001", "to_acct": "1002", "amount": "100"}
    )
    html = resp.get_data(as_text=True)
    # The confirmation reports the source's new balance UNCHANGED at $1000.00.
    assert 'id="new_balance">$1000.00' in html
    assert "previous balance" in html.lower()

    # And the dashboard confirms it: Checking still 1000, Savings credited to 600.
    dash = client.get("/dashboard").get_data(as_text=True)
    assert "$1000.00" in dash  # Checking not debited (bug)
    assert "$600.00" in dash   # Savings credited


def test_invalid_amount_rerenders_form_not_deadend():
    client = app.test_client()
    client.post("/login", data={"username": "demo", "password": "demo"})
    resp = client.post(
        "/transfer", data={"from_acct": "1001", "to_acct": "1002", "amount": "abc"}
    )
    html = resp.get_data(as_text=True)
    assert "Invalid amount" in html
    # The form is still present so a tester (or the agent) can retry.
    assert 'id="amount"' in html
    assert 'id="submit"' in html


@pytest.fixture
def live_demo():
    server = make_server("127.0.0.1", 5099, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:5099"
    finally:
        server.shutdown()
        thread.join()


async def test_explorer_captures_planted_bug(page, live_demo, tmp_path):
    tools.instrument(page)
    # Log in via the demo form (Parabank's auth helper doesn't apply here).
    await page.goto(f"{live_demo}/")
    await page.fill("#username", "demo")
    await page.fill("#password", "demo")
    await page.click("#login")
    await page.goto(f"{live_demo}/transfer")

    # Scripted explorer using the demo's stable selectors (incl. the new select).
    llm = FakeLLM([
        ExplorerDecision(reasoning="pick source",
                         action=Action(kind="select", selector="#from_acct", value="1001")),
        ExplorerDecision(reasoning="pick destination",
                         action=Action(kind="select", selector="#to_acct", value="1002")),
        ExplorerDecision(reasoning="enter amount",
                         action=Action(kind="fill", selector="#amount", value="100")),
        ExplorerDecision(reasoning="submit",
                         action=Action(kind="click", selector="#submit")),
        ExplorerDecision(reasoning="report what I saw",
                         action=Action(kind="finish",
                                       value="Transferred $100 from Checking; the new balance still shows $1000.00.")),
    ])

    bundle = await explore(
        page, flow="demo_transfer",
        goal="Transfer $100 from Checking to Savings and verify Checking decreased.",
        llm=llm, settings=RunSettings(max_steps=10), run_dir=tmp_path,
    )

    assert bundle.finished_reason == "agent_finished"
    assert all(s.status == "ok" for s in bundle.steps)
    # The captured final page holds the smoking gun for the judge.
    text = bundle.final_page_state["text"]
    assert "previous balance" in text.lower()
    assert "$1000.00" in text  # source unchanged after a $100 transfer
