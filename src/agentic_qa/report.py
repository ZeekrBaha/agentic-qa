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
