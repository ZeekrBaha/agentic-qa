"""Phase 8 showcase: the agent autonomously finds + classifies the planted bug.

Spins up the demo bank, lets the explorer attempt a transfer, and has the
RAG-grounded judge score the result. The expected outcome: status=fail,
category=data_error — because the source balance never decreased.

    python -m agentic_qa.run_demo        # requires OPENAI_API_KEY

Writes a report to runs/<ts>/.
"""

from __future__ import annotations

import asyncio
import threading

from playwright.async_api import async_playwright
from werkzeug.serving import make_server

from . import config, rag, report, tools
from .demo_app.app import app
from .explorer import explore, new_run_dir
from .judge import judge
from .llm import LLMClient
from .schema import FlowSpec

HOST, PORT = "127.0.0.1", 5005
BASE = f"http://{HOST}:{PORT}"

FLOW = FlowSpec(
    flow="demo_transfer",
    goal=(
        "Transfer $100 from the Checking account to the Savings account, then "
        "confirm that Checking's balance decreased by $100. Report the exact "
        "before and after balances you see."
    ),
)


async def _demo_login(page):
    await page.goto(f"{BASE}/")
    await page.fill("#username", "demo")
    await page.fill("#password", "demo")
    await page.click("#login")
    await page.goto(f"{BASE}/transfer")


async def main() -> None:
    llm = LLMClient()  # fails fast without OPENAI_API_KEY
    run_dir = new_run_dir()

    server = make_server(HOST, PORT, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=config.RUN.headless)
            page = await browser.new_page()
            page.set_default_timeout(config.RUN.action_timeout_ms)
            tools.instrument(page)
            await _demo_login(page)

            bundle = await explore(
                page, flow=FLOW.flow, goal=FLOW.goal, llm=llm, run_dir=run_dir
            )
            await browser.close()
    finally:
        server.shutdown()
        thread.join()

    # Ground the judge in the documented transfer rule.
    store = rag.InMemoryVectorStore()
    await rag.index_expected_behavior(store, llm.embed)
    contexts = await rag.grounded_contexts([FLOW], store, llm.embed)
    verdict = await judge(bundle, llm=llm, extra_context=contexts[FLOW.flow])

    report.render_markdown(
        bundles=[bundle], verdicts=[verdict], run_dir=run_dir, base_url=BASE,
        explorer_model=config.EXPLORER_MODEL, judge_model=config.JUDGE_MODEL,
        usage=llm.usage, timestamp=run_dir.name,
    )
    report.render_html(
        bundles=[bundle], verdicts=[verdict], run_dir=run_dir, base_url=BASE,
        explorer_model=config.EXPLORER_MODEL, judge_model=config.JUDGE_MODEL,
        usage=llm.usage, timestamp=run_dir.name,
    )

    print("\n=== PLANTED-BUG DEMO RESULT ===")
    print(f"Explorer finished: {bundle.finished_reason}")
    print(f"Explorer summary: {bundle.finish_summary}")
    print(f"VERDICT: {verdict.status} / {verdict.category} / {verdict.severity} "
          f"(confidence {verdict.confidence:.2f})")
    print(f"Judge reasoning: {verdict.reasoning}")
    print(f"Tokens: {llm.usage}")
    print(f"Report: {run_dir / 'report.md'}")


if __name__ == "__main__":
    asyncio.run(main())
