"""Job searches started from the app (see ``job_cannon.job_search_run``).

A run records its progress steps while Claude works, then the final report.
The applications it added are the ones created after it started.
"""

import sqlite3

from job_cannon.db import now
from job_cannon.repo import applications

STATUSES = ["running", "done", "failed", "cancelled"]
MAX_JOBS = 10
MAX_FOCUS_CHARS = 300


def start(conn, job_count, focus: str = "") -> int:
    try:
        job_count = int(job_count)
    except (TypeError, ValueError):
        raise ValueError("Choose how many jobs to look for") from None
    if not 1 <= job_count <= MAX_JOBS:
        raise ValueError(f"Choose between 1 and {MAX_JOBS} jobs")
    focus = " ".join((focus or "").split())
    if len(focus) > MAX_FOCUS_CHARS:
        raise ValueError(f"Keep the focus under {MAX_FOCUS_CHARS} characters")
    with conn:
        before = conn.execute("SELECT COALESCE(MAX(id), 0) FROM applications").fetchone()[0]
        return conn.execute(
            "INSERT INTO search_runs (job_count, focus, max_app_id_before, started_at) VALUES (?, ?, ?, ?)",
            (job_count, focus, before, now()),
        ).lastrowid


def add_step(conn, run_id: int, step: str) -> None:
    with conn:
        conn.execute(
            "UPDATE search_runs SET steps = steps || ? WHERE id = ?",
            (" ".join(step.split()) + "\n", run_id),
        )


def finish(conn, run_id: int, status: str, report: str = "", error: str = "") -> None:
    if status not in STATUSES or status == "running":
        raise ValueError(f"unknown final status: {status}")
    with conn:
        conn.execute(
            "UPDATE search_runs SET status = ?, report = ?, error = ?, finished_at = ? WHERE id = ?",
            (status, report.strip(), error.strip(), now(), run_id),
        )


def get(conn, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM search_runs WHERE id = ?", (run_id,)).fetchone()


def latest(conn) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM search_runs ORDER BY id DESC LIMIT 1").fetchone()


def steps(run) -> list[str]:
    return [s for s in run["steps"].split("\n") if s]


def added_applications(conn, run) -> list[sqlite3.Row]:
    """Applications created since the run started (by the run, unless added by hand meanwhile)."""
    sql = applications._SELECT + " WHERE a.id > ? AND a.created_at >= ? ORDER BY a.id"
    return conn.execute(sql, (run["max_app_id_before"], run["started_at"])).fetchall()


def fail_running(conn) -> None:
    """A restart ends the Claude process, so a run still marked running never finishes."""
    with conn:
        conn.execute(
            "UPDATE search_runs SET status = 'failed', error = 'Job Cannon was closed while this search was running.',"
            " finished_at = ? WHERE status = 'running'",
            (now(),),
        )
