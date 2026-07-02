"""Offline tests for the markdown + HTML report renderers."""

from __future__ import annotations

from pathlib import Path

from agentic_qa.judge import Verdict
from agentic_qa.report import render_html, render_markdown
from agentic_qa.schema import ObservationBundle

FIXTURES = Path(__file__).parent / "fixtures"


def _data():
    good = ObservationBundle.model_validate_json((FIXTURES / "bundle_good_transfer.json").read_text())
    broken = ObservationBundle.model_validate_json((FIXTURES / "bundle_broken_billpay.json").read_text())
    verdicts = [
        Verdict(status="pass", category="functional", severity="low",
                reasoning="confirmation shown", confidence=0.9),
        Verdict(status="fail", category="crash", severity="high",
                reasoning="500 + NullPointerException", confidence=0.95),
    ]
    return [good, broken], verdicts


def test_render_markdown(tmp_path):
    bundles, verdicts = _data()
    path = render_markdown(
        bundles=bundles, verdicts=verdicts, run_dir=tmp_path,
        base_url="http://localhost:8080/parabank",
        explorer_model="gpt-4o-mini", judge_model="gpt-4o",
        usage={"total_tokens": 1234, "calls": 4}, timestamp="20260530-000000",
    )
    text = path.read_text()
    assert path.name == "report.md"
    assert "1 pass, 1 fail" in text
    assert "transfer" in text and "billpay" in text
    assert "500 + NullPointerException" in text
    assert "1234" in text


def test_render_html_renders_console_errors_as_readable_text(tmp_path):
    bundles, verdicts = _data()
    path = render_html(
        bundles=bundles, verdicts=verdicts, run_dir=tmp_path,
        base_url="http://localhost:8080/parabank",
        explorer_model="gpt-4o-mini", judge_model="gpt-4o",
        usage={"total_tokens": 1234, "calls": 4}, timestamp="20260530-000000",
    )
    html = path.read_text()
    broken = bundles[1]
    assert broken.console_errors, "fixture must have console errors to exercise this path"
    errors_html = html.split("<b>Errors:</b>")[1].split("</p>")[0]
    # Console errors must render as readable joined text, not a Python list repr.
    assert "[" not in errors_html
    for err in broken.console_errors:
        assert err in errors_html


def test_render_html_escapes_and_writes(tmp_path):
    bundles, verdicts = _data()
    path = render_html(
        bundles=bundles, verdicts=verdicts, run_dir=tmp_path,
        base_url="http://localhost:8080/parabank",
        explorer_model="gpt-4o-mini", judge_model="gpt-4o",
        usage={"total_tokens": 1234, "calls": 4}, timestamp="20260530-000000",
    )
    html = path.read_text()
    assert path.name == "report.html"
    assert "<table>" in html and "Agentic QA Report" in html
    assert "transfer" in html and "billpay" in html
    # HTML-escaping is applied to reasoning text.
    assert "&lt;" not in "no-angle-brackets-here"  # sanity
