"""Run history in SQLite — observability over time.

Every QA run logs one ``runs`` row plus one ``flow_results`` row per flow. That
gives a small but real relational dataset to aggregate over: pass-rates per
flow, severity counts, and a runs-to-results join for the most recent failures.
Uses only the stdlib ``sqlite3``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .judge import Verdict
from .schema import ObservationBundle

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    base_url      TEXT NOT NULL,
    explorer_model TEXT,
    judge_model   TEXT,
    total_tokens  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS flow_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    flow            TEXT NOT NULL,
    status          TEXT NOT NULL,
    category        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    finished_reason TEXT,
    n_steps         INTEGER,
    n_console_errors INTEGER,
    n_network_failures INTEGER,
    reasoning       TEXT
);
"""


def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open (and initialize) the history database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def record_run(
    conn: sqlite3.Connection,
    *,
    ts: str,
    base_url: str,
    explorer_model: str,
    judge_model: str,
    bundles: list[ObservationBundle],
    verdicts: list[Verdict],
    usage: dict[str, Any] | None = None,
) -> int:
    """Insert one run and its per-flow results. Returns the run id."""
    cur = conn.execute(
        "INSERT INTO runs (ts, base_url, explorer_model, judge_model, total_tokens) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts, base_url, explorer_model, judge_model,
         (usage or {}).get("total_tokens", 0)),
    )
    run_id = int(cur.lastrowid)
    for b, v in zip(bundles, verdicts):
        conn.execute(
            "INSERT INTO flow_results (run_id, flow, status, category, severity, "
            "confidence, finished_reason, n_steps, n_console_errors, "
            "n_network_failures, reasoning) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, b.flow, v.status, v.category, v.severity, v.confidence,
             b.finished_reason, len(b.steps), len(b.console_errors),
             len(b.network_failures), v.reasoning),
        )
    conn.commit()
    return run_id


def pass_rate_by_flow(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Aggregate pass-rate per flow across all recorded runs."""
    rows = conn.execute(
        """
        SELECT flow,
               COUNT(*)                                   AS runs,
               SUM(status = 'pass')                       AS passes,
               SUM(status = 'fail')                       AS fails,
               ROUND(AVG(status = 'pass') * 100, 1)       AS pass_rate_pct
        FROM flow_results
        GROUP BY flow
        ORDER BY pass_rate_pct ASC, flow
        """
    ).fetchall()
    return [dict(r) for r in rows]


def severity_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Count non-passing results by severity."""
    rows = conn.execute(
        "SELECT severity, COUNT(*) AS n FROM flow_results "
        "WHERE status = 'fail' GROUP BY severity"
    ).fetchall()
    return {r["severity"]: r["n"] for r in rows}


def recent_failures(conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    """Most recent failing flows, joined to their run's timestamp/model."""
    rows = conn.execute(
        """
        SELECT r.ts, r.judge_model, f.flow, f.severity, f.category, f.reasoning
        FROM flow_results f
        JOIN runs r ON r.id = f.run_id
        WHERE f.status = 'fail'
        ORDER BY r.id DESC, f.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def default_db_path() -> Path:
    from . import config
    return config.runs_dir() / "history.db"
