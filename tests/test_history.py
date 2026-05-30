"""Offline tests for SQLite run history + aggregate queries."""

from __future__ import annotations

from pathlib import Path

from agentic_qa import history
from agentic_qa.judge import Verdict
from agentic_qa.schema import ObservationBundle

FIXTURES = Path(__file__).parent / "fixtures"


def _bundles():
    good = ObservationBundle.model_validate_json((FIXTURES / "bundle_good_transfer.json").read_text())
    broken = ObservationBundle.model_validate_json((FIXTURES / "bundle_broken_billpay.json").read_text())
    return good, broken


def _seed(conn):
    good, broken = _bundles()
    v_pass = Verdict(status="pass", category="functional", severity="low",
                     reasoning="ok", confidence=0.9)
    v_fail = Verdict(status="fail", category="crash", severity="high",
                     reasoning="500 error on billpay", confidence=0.95)
    # Run 1: transfer pass, billpay fail
    history.record_run(conn, ts="20260530-000001", base_url="http://x",
                       explorer_model="gpt-4o-mini", judge_model="gpt-4o",
                       bundles=[good, broken], verdicts=[v_pass, v_fail],
                       usage={"total_tokens": 1000})
    # Run 2: transfer fail this time
    history.record_run(conn, ts="20260530-000002", base_url="http://x",
                       explorer_model="gpt-4o-mini", judge_model="gpt-4o",
                       bundles=[good], verdicts=[Verdict(
                           status="fail", category="data_error", severity="medium",
                           reasoning="balance unchanged", confidence=0.8)],
                       usage={"total_tokens": 500})


def test_record_and_pass_rate_by_flow():
    conn = history.connect(":memory:")
    _seed(conn)
    rates = {r["flow"]: r for r in history.pass_rate_by_flow(conn)}
    # transfer: 1 pass of 2 runs = 50%
    assert rates["transfer"]["runs"] == 2
    assert rates["transfer"]["passes"] == 1
    assert rates["transfer"]["pass_rate_pct"] == 50.0
    # billpay: 0 of 1 = 0%
    assert rates["billpay"]["pass_rate_pct"] == 0.0


def test_severity_counts_and_recent_failures():
    conn = history.connect(":memory:")
    _seed(conn)
    sev = history.severity_counts(conn)
    assert sev == {"high": 1, "medium": 1}

    fails = history.recent_failures(conn, limit=10)
    # Most recent run first (run 2: transfer data_error).
    assert fails[0]["flow"] == "transfer"
    assert fails[0]["category"] == "data_error"
    assert all(f["ts"] for f in fails)  # join brought the timestamp through
    assert len(fails) == 2
