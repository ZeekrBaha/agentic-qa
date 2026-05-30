"""Render flow results (bundle + verdict pairs) to a human-readable report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .judge import Verdict
from .schema import ObservationBundle

_STATUS_EMOJI = {"pass": "✅", "fail": "❌", "uncertain": "❓"}


def _summary_row(bundle: ObservationBundle, verdict: Verdict) -> str:
    emoji = _STATUS_EMOJI.get(verdict.status, "")
    return (
        f"| {bundle.flow} | {emoji} {verdict.status} | {verdict.category} | "
        f"{verdict.severity} | {verdict.confidence:.2f} |"
    )


def _flow_section(bundle: ObservationBundle, verdict: Verdict) -> str:
    lines = [
        f"### {bundle.flow} — {verdict.status.upper()}",
        "",
        f"- **Goal:** {bundle.goal}",
        f"- **Finished:** {bundle.finished_reason} after {len(bundle.steps)} step(s)",
        f"- **Console errors:** {len(bundle.console_errors)} | "
        f"**Network failures:** {len(bundle.network_failures)}",
        f"- **Verdict:** {verdict.status} / {verdict.category} / {verdict.severity} "
        f"(confidence {verdict.confidence:.2f})",
        f"- **Judge reasoning:** {verdict.reasoning}",
    ]
    if bundle.finish_summary:
        lines.append(f"- **Explorer summary:** {bundle.finish_summary}")
    if bundle.console_errors:
        lines.append(f"- **Errors seen:** {bundle.console_errors}")
    for shot in bundle.screenshots:
        lines.append(f"- **Screenshot:** `{shot}`")
    lines.append("")
    return "\n".join(lines)


def render_markdown(
    *,
    bundles: list[ObservationBundle],
    verdicts: list[Verdict],
    run_dir: Path,
    base_url: str,
    explorer_model: str,
    judge_model: str,
    usage: dict[str, Any] | None = None,
    timestamp: str = "",
) -> Path:
    """Write report.md to run_dir and return its path."""
    passed = sum(1 for v in verdicts if v.status == "pass")
    failed = sum(1 for v in verdicts if v.status == "fail")
    uncertain = sum(1 for v in verdicts if v.status == "uncertain")

    parts = [
        "# Agentic QA Report",
        "",
        f"- **Target:** {base_url}",
        f"- **Explorer model:** {explorer_model} | **Judge model:** {judge_model}",
    ]
    if timestamp:
        parts.append(f"- **Run:** {timestamp}")
    if usage:
        parts.append(f"- **Tokens:** {usage.get('total_tokens', 0)} "
                     f"({usage.get('calls', 0)} LLM calls)")
    parts += [
        f"- **Flows tested:** {len(verdicts)} — "
        f"{passed} pass, {failed} fail, {uncertain} uncertain",
        "",
        "## Summary",
        "",
        "| Flow | Status | Category | Severity | Confidence |",
        "| --- | --- | --- | --- | --- |",
        *[_summary_row(b, v) for b, v in zip(bundles, verdicts)],
        "",
        "## Details",
        "",
        *[_flow_section(b, v) for b, v in zip(bundles, verdicts)],
    ]
    out = run_dir / "report.md"
    out.write_text("\n".join(parts))
    return out


_HTML_COLORS = {"pass": "#1a7f37", "fail": "#cf222e", "uncertain": "#9a6700"}


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_html(
    *,
    bundles: list[ObservationBundle],
    verdicts: list[Verdict],
    run_dir: Path,
    base_url: str,
    explorer_model: str,
    judge_model: str,
    usage: dict[str, Any] | None = None,
    timestamp: str = "",
) -> Path:
    """Write a self-contained report.html (no external deps) and return its path."""
    passed = sum(1 for v in verdicts if v.status == "pass")
    failed = sum(1 for v in verdicts if v.status == "fail")
    uncertain = sum(1 for v in verdicts if v.status == "uncertain")

    rows = "".join(
        f"<tr><td>{_esc(b.flow)}</td>"
        f"<td style='color:{_HTML_COLORS.get(v.status, '#000')};font-weight:600'>"
        f"{_STATUS_EMOJI.get(v.status, '')} {v.status}</td>"
        f"<td>{v.category}</td><td>{v.severity}</td><td>{v.confidence:.2f}</td></tr>"
        for b, v in zip(bundles, verdicts)
    )

    cards = []
    for b, v in zip(bundles, verdicts):
        color = _HTML_COLORS.get(v.status, "#000")
        cards.append(
            f"<div class='card'><h3 style='border-left:4px solid {color}'>"
            f"{_esc(b.flow)} — <span style='color:{color}'>{v.status.upper()}</span></h3>"
            f"<p><b>Goal:</b> {_esc(b.goal)}</p>"
            f"<p><b>Finished:</b> {b.finished_reason} after {len(b.steps)} step(s) | "
            f"console errors: {len(b.console_errors)} | network failures: "
            f"{len(b.network_failures)}</p>"
            f"<p><b>Verdict:</b> {v.category} / {v.severity} "
            f"(confidence {v.confidence:.2f})</p>"
            f"<p><b>Judge reasoning:</b> {_esc(v.reasoning)}</p>"
            + (f"<p><b>Explorer summary:</b> {_esc(b.finish_summary)}</p>"
               if b.finish_summary else "")
            + (f"<p><b>Errors:</b> {_esc(b.console_errors)}</p>"
               if b.console_errors else "")
            + "".join(
                f"<img src='{_esc(Path(s).name)}' style='max-width:100%;border:1px solid #ddd'>"
                for s in b.screenshots
            )
            + "</div>"
        )

    tokens = f"{usage.get('total_tokens', 0)} ({usage.get('calls', 0)} calls)" if usage else "n/a"
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Agentic QA Report</title>
<style>
 body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px;
        margin: 2rem auto; padding: 0 1rem; color: #1f2328; }}
 table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
 th, td {{ border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }}
 th {{ background: #f6f8fa; }}
 .card {{ background: #f6f8fa; border-radius: 8px; padding: 1rem; margin: 1rem 0; }}
 .card h3 {{ padding-left: 10px; margin-top: 0; }}
 .meta {{ color: #57606a; font-size: 0.9rem; }}
</style></head><body>
<h1>Agentic QA Report</h1>
<p class="meta">Target: {_esc(base_url)} &middot; Explorer: {explorer_model} &middot;
 Judge: {judge_model} &middot; Tokens: {tokens} &middot; Run: {_esc(timestamp)}</p>
<p><b>{len(verdicts)} flows tested</b> — {passed} pass, {failed} fail, {uncertain} uncertain</p>
<h2>Summary</h2>
<table><tr><th>Flow</th><th>Status</th><th>Category</th><th>Severity</th><th>Confidence</th></tr>
{rows}</table>
<h2>Details</h2>
{''.join(cards)}
</body></html>"""
    out = run_dir / "report.html"
    out.write_text(html)
    return out
