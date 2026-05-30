"""Command-line entry point.

    agentic-qa list-flows
    agentic-qa run                      # all default flows
    agentic-qa run --flows transfer,billpay --headed

Requires OPENAI_API_KEY and a reachable Parabank.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from playwright.async_api import async_playwright

from . import config, flows, history, report, tools
from .auth import ensure_logged_in
from .explorer import new_run_dir
from .graph import run_qa
from .llm import LLMClient
from .schema import FlowSpec

app = typer.Typer(add_completion=False, help="Agentic QA — explorer + judge over Parabank.")


@app.command("list-flows")
def list_flows() -> None:
    """List the available test flows."""
    for f in flows.DEFAULT_FLOWS:
        typer.echo(f"{f.flow:18s} {f.goal}")


async def _run(flow_specs: list[FlowSpec], headed: bool, base_url: str) -> Path:
    llm = LLMClient()  # fails fast if OPENAI_API_KEY is unset
    run_dir = new_run_dir()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        page = await browser.new_page()
        page.set_default_timeout(config.RUN.action_timeout_ms)
        tools.instrument(page)
        await ensure_logged_in(page)

        state = await run_qa(
            page=page, llm=llm, flows=flow_specs, run_dir=run_dir, base_url=base_url
        )
        await browser.close()

    report.render_html(
        bundles=state["bundles"],
        verdicts=state["verdicts"],
        run_dir=run_dir,
        base_url=base_url,
        explorer_model=config.EXPLORER_MODEL,
        judge_model=config.JUDGE_MODEL,
        usage=llm.usage,
        timestamp=run_dir.name,
    )

    conn = history.connect(history.default_db_path())
    history.record_run(
        conn, ts=run_dir.name, base_url=base_url,
        explorer_model=config.EXPLORER_MODEL, judge_model=config.JUDGE_MODEL,
        bundles=state["bundles"], verdicts=state["verdicts"], usage=llm.usage,
    )
    conn.close()

    typer.echo("")
    for b, v in zip(state["bundles"], state["verdicts"]):
        typer.echo(f"  {b.flow:18s} {v.status:9s} {v.category}/{v.severity} "
                   f"(conf {v.confidence:.2f})")
    typer.echo(f"\nTokens: {llm.usage}")
    typer.echo(f"Report: {run_dir / 'report.md'}")
    typer.echo(f"        {run_dir / 'report.html'}")
    return run_dir


@app.command()
def run(
    flow_names: str = typer.Option(
        None, "--flows", help="Comma-separated flow names (default: all)."
    ),
    headed: bool = typer.Option(False, "--headed", help="Show the browser window."),
    base_url: str = typer.Option(config.BASE_URL, "--base-url", help="Parabank base URL."),
) -> None:
    """Explore the selected flows and judge each one."""
    names = [n.strip() for n in flow_names.split(",")] if flow_names else None
    try:
        flow_specs = flows.select(names)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    asyncio.run(_run(flow_specs, headed, base_url))


@app.command("history")
def show_history() -> None:
    """Show aggregate stats across recorded runs."""
    db = history.default_db_path()
    if not db.exists():
        typer.echo("No run history yet. Run `agentic-qa run` first.")
        return
    conn = history.connect(db)
    typer.echo("Pass-rate by flow:")
    for row in history.pass_rate_by_flow(conn):
        typer.echo(f"  {row['flow']:18s} {row['pass_rate_pct']:5.1f}%  "
                   f"({row['passes']}/{row['runs']} runs)")
    sev = history.severity_counts(conn)
    if sev:
        typer.echo(f"\nFailures by severity: {sev}")
    fails = history.recent_failures(conn, limit=5)
    if fails:
        typer.echo("\nRecent failures:")
        for f in fails:
            typer.echo(f"  [{f['ts']}] {f['flow']} ({f['severity']}/{f['category']}): "
                       f"{f['reasoning'][:80]}")
    conn.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
